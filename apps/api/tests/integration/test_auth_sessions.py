"""Authentication, sessions, CSRF and origin checks through the real HTTP stack."""

import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from app.modules.audit.models import AuditEvent
from app.modules.auth.crypto import digest, hash_password
from app.modules.auth.models import (
    AuthSession,
    MemberInviteToken,
    PasswordResetToken,
    UserCredential,
    UserFace,
    UserPasskey,
)
from app.modules.memberships.models import Membership
from app.modules.users.models import PlatformUser
from tests.support.outbox import invite_token, sent_to
from tests.support.workspace import PASSWORD, add_member, error_code, unique

pytestmark = pytest.mark.integration

LINK_TOKEN = re.compile(r"[?&]token=([^&\s]+)")


def cookie_attributes(response, name):
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{name}="):
            return {part.strip().lower() for part in header.split(";")[1:]}
    raise AssertionError(f"{name} cookie not set")


async def db_scalar(stack, statement):
    return await stack.app.state.test_connection.scalar(statement)


async def db_execute(stack, statement):
    await stack.app.state.test_connection.execute(statement)


async def test_register_sets_hardened_cookies_and_stores_only_digests(stack):
    async with stack.browser() as browser:
        email = f"{unique('reg')}@example.com"
        response = await browser.post(
            "/api/v1/auth/register",
            json={
                "email": email.upper(),
                "password": PASSWORD,
                "display_name": "Reg",
                "organization_name": unique("Org"),
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["user"]["email"] == email  # normalized
        assert body["roles"] == ["owner"] and body["tenant"] and body["environment"]
        assert PASSWORD not in response.text and "hash" not in response.text

        session_cookie = cookie_attributes(response, "platform_session")
        assert {"httponly", "samesite=lax", "path=/"} <= session_cookie
        csrf_cookie = cookie_attributes(response, "platform_csrf")
        assert "httponly" not in csrf_cookie and "samesite=strict" in csrf_cookie

        token = browser.cookies["platform_session"]
        csrf = browser.cookies["platform_csrf"]
        user_id = body["user"]["id"]
        stored = await db_scalar(
            stack, select(AuthSession.token_hash).where(AuthSession.user_id == user_id)
        )
        assert stored == digest(token) and stored != token
        assert await db_scalar(
            stack, select(AuthSession.csrf_hash).where(AuthSession.user_id == user_id)
        ) == digest(csrf)
        assert (
            await db_scalar(stack, select(AuthSession.id).where(AuthSession.token_hash == token))
            is None
        )
        password_hash = await db_scalar(
            stack, select(UserCredential.password_hash).where(UserCredential.user_id == user_id)
        )
        assert password_hash.startswith("$argon2id$") and PASSWORD not in password_hash

        duplicate = await browser.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": PASSWORD,
                "display_name": "Again",
                "organization_name": unique("Org"),
            },
        )
        assert duplicate.status_code == 409


@pytest.mark.parametrize(
    "password", ["Qz9!x", "aaaaaaaaaaaaaaaa", "abababababababab"], ids=["short", "one", "two"]
)
async def test_weak_passwords_are_rejected(stack, password):
    async with stack.browser() as browser:
        response = await browser.post(
            "/api/v1/auth/register",
            json={
                "email": f"{unique('weak')}@example.com",
                "password": password,
                "display_name": "Weak",
                "organization_name": unique("Org"),
            },
        )
        assert response.status_code == 422
        assert password not in response.text


async def test_login_wrong_password_and_unknown_account_look_identical(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        wrong = await browser.post(
            "/api/v1/auth/login", json={"email": owner.email, "password": "Wrong-Password-1"}
        )
        unknown = await browser.post(
            "/api/v1/auth/login",
            json={"email": f"{unique('nobody')}@example.com", "password": "Wrong-Password-1"},
        )
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json()["error"]["code"] == unknown.json()["error"]["code"] == "UNAUTHORIZED"
        assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]
        assert "set-cookie" not in wrong.headers


async def test_lockout_after_repeated_failures_blocks_correct_password(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
    user_id = owner.session["user"]["id"]
    async with stack.browser() as attacker:
        for _ in range(4):
            response = await attacker.post(
                "/api/v1/auth/login", json={"email": owner.email, "password": "Nope-nope-123"}
            )
            assert response.status_code == 401
        # A success before the threshold resets the counter.
        await stack.login(attacker, owner.email)
        assert (
            await db_scalar(
                stack,
                select(UserCredential.failed_attempts).where(UserCredential.user_id == user_id),
            )
            == 0
        )
        attacker.cookies.clear()
        for _ in range(5):  # login_max_failures default
            await attacker.post(
                "/api/v1/auth/login", json={"email": owner.email, "password": "Nope-nope-123"}
            )
        locked = await attacker.post(
            "/api/v1/auth/login", json={"email": owner.email, "password": PASSWORD}
        )
        assert locked.status_code == 401 and "set-cookie" not in locked.headers
        locked_until = await db_scalar(
            stack, select(UserCredential.locked_until).where(UserCredential.user_id == user_id)
        )
        assert locked_until is not None and locked_until > datetime.now(UTC)
        # Once the lock expires the correct password works again.
        await db_execute(
            stack,
            update(UserCredential)
            .where(UserCredential.user_id == user_id)
            .values(locked_until=datetime.now(UTC) - timedelta(seconds=1)),
        )
        await stack.login(attacker, owner.email)


async def test_session_resolution_rejects_missing_forged_revoked_and_expired_tokens(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        assert (await owner.get("auth/session")).status_code == 200
        token = browser.cookies["platform_session"]
        user_id = owner.session["user"]["id"]

    async with stack.browser() as other:
        assert (await other.get("/api/v1/auth/session")).status_code == 401
        for forged in ("x" * 43, "x" * 200, digest(token)):  # includes the stored digest
            other.cookies.set("platform_session", forged)
            response = await other.get("/api/v1/auth/session")
            assert response.status_code == 401 and error_code(response) == "UNAUTHORIZED"
        # Identity headers never select a user.
        other.cookies.clear()
        response = await other.get("/api/v1/customers", headers={"x-user-id": user_id})
        assert response.status_code == 401

        other.cookies.set("platform_session", token)
        assert (await other.get("/api/v1/auth/session")).status_code == 200
        await db_execute(
            stack,
            update(AuthSession)
            .where(AuthSession.token_hash == digest(token))
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1)),
        )
        assert (await other.get("/api/v1/auth/session")).status_code == 401
        await db_execute(
            stack,
            update(AuthSession)
            .where(AuthSession.token_hash == digest(token))
            .values(expires_at=datetime.now(UTC) + timedelta(hours=1)),
        )
        assert (await other.get("/api/v1/auth/session")).status_code == 200
        await db_execute(
            stack, update(PlatformUser).where(PlatformUser.id == user_id).values(status="inactive")
        )
        assert (await other.get("/api/v1/auth/session")).status_code == 401


async def test_logout_revokes_only_that_session_and_logout_all_revokes_every_session(stack):
    async with stack.browser() as first, stack.browser() as second, stack.browser() as third:
        owner = await stack.register(first)
        two = await stack.login(second, owner.email)
        three = await stack.login(third, owner.email)
        stolen = first.cookies["platform_session"]

        response = await owner.post("auth/logout")
        assert response.status_code == 204
        cleared = response.headers.get_list("set-cookie")
        assert any(h.startswith("platform_session=") and "Max-Age=0" in h for h in cleared)
        # Replaying the old cookie after logout is useless.
        first.cookies.set("platform_session", stolen)
        assert (await first.get("/api/v1/auth/session")).status_code == 401
        assert (await two.get("auth/session")).status_code == 200

        assert (await two.post("auth/logout-all")).status_code == 204
        assert (await two.get("auth/session")).status_code == 401
        assert (await three.get("auth/session")).status_code == 401


async def test_password_change_requires_current_password_and_revokes_other_sessions(stack):
    async with stack.browser() as first, stack.browser() as second:
        owner = await stack.register(first)
        other = await stack.login(second, owner.email)
        wrong = await owner.post(
            "auth/password",
            {"current_password": "Not-the-password-1", "new_password": "Brand-New-Secret-77"},
        )
        assert wrong.status_code == 422 and error_code(wrong) == "INVALID_CREDENTIALS"
        assert (await other.get("auth/session")).status_code == 200  # nothing revoked

        weak = await owner.post(
            "auth/password", {"current_password": PASSWORD, "new_password": "short"}
        )
        assert weak.status_code == 422

        changed = await owner.post(
            "auth/password",
            {"current_password": PASSWORD, "new_password": "Brand-New-Secret-77"},
        )
        assert changed.status_code == 204
        assert (await owner.get("auth/session")).status_code == 200
        assert (await other.get("auth/session")).status_code == 401

    async with stack.browser() as fresh:
        old = await fresh.post(
            "/api/v1/auth/login", json={"email": owner.email, "password": PASSWORD}
        )
        assert old.status_code == 401
        await stack.login(fresh, owner.email, "Brand-New-Secret-77")


async def test_csrf_is_required_and_bound_to_the_session(stack):
    async with stack.browser() as first, stack.browser() as second:
        owner = await stack.register(first)
        other = await stack.register(second)
        body = {"name": "CSRF probe"}

        first.headers.pop("x-csrf-token")
        missing = await owner.post("customers", body)
        assert missing.status_code == 403 and error_code(missing) == "CSRF_FAILED"
        # A valid token from a different session does not transfer.
        first.headers["x-csrf-token"] = second.cookies["platform_csrf"]
        foreign = await owner.post("customers", body)
        assert foreign.status_code == 403 and error_code(foreign) == "CSRF_FAILED"
        first.headers["x-csrf-token"] = "x" * 500
        assert (await owner.post("customers", body)).status_code == 403
        for method, path in (
            ("PATCH", "settings/business"),
            ("PUT", "auth/session/workspace"),
            ("POST", "auth/logout"),
            ("POST", "auth/logout-all"),
            ("DELETE", f"members/{uuid4()}"),
        ):
            response = await first.request(method, f"/api/v1/{path}", json={})
            assert response.status_code == 403, (method, path)
        # Safe methods do not need the token; nothing was created by the rejected calls.
        listing = await owner.get("customers")
        assert listing.status_code == 200 and listing.json()["total"] == 0
        assert (await owner.get("auth/session")).status_code == 200  # logout was blocked

        owner.use_csrf()
        assert (await owner.post("customers", body)).status_code == 201
        assert (await other.get("customers")).json()["total"] == 0


async def test_foreign_origin_is_rejected_even_with_valid_csrf(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        evil = await owner.post(
            "customers", {"name": "Cross-site"}, headers={"origin": "https://evil.example"}
        )
        assert evil.status_code == 403 and error_code(evil) == "FORBIDDEN"
        evil_login = await browser.post(
            "/api/v1/auth/login",
            json={"email": owner.email, "password": PASSWORD},
            headers={"origin": "https://evil.example"},
        )
        assert evil_login.status_code == 403
        assert (await owner.get("customers")).json()["total"] == 0
        # Reads are unaffected, and trailing slashes on an allowed origin are accepted.
        assert (
            await owner.get("customers", headers={"origin": "https://evil.example"})
        ).status_code == 200
        assert (
            await owner.post(
                "customers", {"name": "Same site"}, headers={"origin": "http://localhost:3000/"}
            )
        ).status_code == 201


async def test_workspace_switch_only_to_memberships_and_environments_held(stack):
    async with stack.browser() as a_browser, stack.browser() as b_browser:
        alice = await stack.register(a_browser)
        bob = await stack.register(b_browser)
        staging = await bob.create(
            "environments", {"key": "staging", "name": "Staging", "kind": "staging"}
        )
        for tenant, environment in (
            (bob.tenant_id, None),
            (bob.tenant_id, bob.environment_id),
            (alice.tenant_id, bob.environment_id),
            (alice.tenant_id, staging["id"]),
            (str(uuid4()), None),
        ):
            response = await alice.put(
                "auth/session/workspace", {"tenant_id": tenant, "environment_id": environment}
            )
            assert response.status_code == 404, (tenant, environment)
        extra = await alice.put(
            "auth/session/workspace", {"tenant_id": alice.tenant_id, "user_id": bob.tenant_id}
        )
        assert extra.status_code == 422
        session = (await alice.get("auth/session")).json()
        assert session["tenant"]["id"] == alice.tenant_id

        # Bob adds Alice as a viewer: now she may switch, and loses it again on revocation.
        # (Verified mailbox: an unverified one is reset and re-invited instead, see SEC-1.)
        await verify_email_in_db(stack, alice.email)
        own_tenant = alice.tenant_id
        roles = {r["key"]: r["id"] for r in (await bob.get("roles")).json()}
        member = await bob.create(
            "members",
            {"email": alice.email, "display_name": "Alice", "role_ids": [roles["viewer"]]},
        )
        switched = await alice.switch(bob.tenant_id, staging["id"])
        assert switched["roles"] == ["viewer"] and switched["environment"]["key"] == "staging"
        assert "customers.write" not in switched["permissions"]
        assert (await alice.post("customers", {"name": "Denied"})).status_code == 403
        assert (await bob.delete(f"members/{member['membership_id']}")).status_code == 204
        response = await alice.put("auth/session/workspace", {"tenant_id": bob.tenant_id})
        assert response.status_code == 404
        assert (await alice.get("customers")).status_code == 409
        await alice.switch(own_tenant)
        assert (await alice.get("customers")).status_code == 200


@pytest.fixture
def captured_emails(monkeypatch):
    """Replace the real SMTP send with a recorder: no network call, no SMTP config
    needed, and the test can read the token out of the link it was given."""
    sent: list[dict] = []

    async def fake(settings, http, template, to, variables, **kwargs):
        sent.append({"template": template, "to": list(to), "variables": dict(variables)})

    monkeypatch.setattr("app.modules.auth.service.send_platform_template", fake)
    return sent


async def test_forgot_password_is_silent_about_account_existence_and_only_emails_real_ones(
    stack, captured_emails
):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
    captured_emails.clear()  # drop the sign-up verification email; not what this test checks
    async with stack.browser() as anon:
        known = await anon.post("/api/v1/auth/forgot-password", json={"email": owner.email.upper()})
        unknown = await anon.post(
            "/api/v1/auth/forgot-password", json={"email": f"{unique('nobody')}@example.com"}
        )
        assert known.status_code == unknown.status_code == 204
        assert len(captured_emails) == 1  # only the real account triggers an email
        sent = captured_emails[0]
        assert sent["template"] == "password_reset" and sent["to"] == [owner.email]
        assert sent["variables"]["minutes"] == "30"


async def test_reset_password_flow_sets_new_password_and_revokes_every_session(
    stack, captured_emails
):
    async with stack.browser() as first, stack.browser() as second, stack.browser() as anon:
        owner = await stack.register(first)
        other = await stack.login(second, owner.email)
        captured_emails.clear()  # drop the sign-up verification email

        assert (
            await anon.post("/api/v1/auth/forgot-password", json={"email": owner.email})
        ).status_code == 204
        link = captured_emails[0]["variables"]["link"]
        token = LINK_TOKEN.search(link).group(1)

        weak = await anon.post(
            "/api/v1/auth/reset-password", json={"token": token, "new_password": "short"}
        )
        assert weak.status_code == 422

        bad_token = await anon.post(
            "/api/v1/auth/reset-password",
            json={"token": "not-a-real-token", "new_password": PASSWORD},
        )
        assert bad_token.status_code == 422 and error_code(bad_token) == "INVALID_RESET_TOKEN"

        new_password = "Freshly-Reset-Secret-5"
        reset = await anon.post(
            "/api/v1/auth/reset-password", json={"token": token, "new_password": new_password}
        )
        assert reset.status_code == 204

        # Single-use: the same token cannot be replayed.
        replay = await anon.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": "Another-One-99"},
        )
        assert replay.status_code == 422 and error_code(replay) == "INVALID_RESET_TOKEN"

        # Every session open before the reset was ended.
        assert (await other.get("auth/session")).status_code == 401

    async with stack.browser() as fresh:
        old = await fresh.post(
            "/api/v1/auth/login", json={"email": owner.email, "password": PASSWORD}
        )
        assert old.status_code == 401
        await stack.login(fresh, owner.email, new_password)


async def test_reset_password_token_cannot_be_used_once_expired(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
    user_id = owner.session["user"]["id"]
    token = "x" * 43
    await db_execute(
        stack,
        PasswordResetToken.__table__.insert().values(
            user_id=user_id,
            token_hash=digest(token),
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        ),
    )
    async with stack.browser() as anon:
        response = await anon.post(
            "/api/v1/auth/reset-password", json={"token": token, "new_password": PASSWORD}
        )
        assert response.status_code == 422 and error_code(response) == "INVALID_RESET_TOKEN"


async def test_member_invited_by_email_accepts_and_signs_in(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        email = await add_member(owner, ["viewer"], password="Initial-Secret-42")
    async with stack.browser() as browser:
        member = await stack.login(browser, email, "Initial-Secret-42")
        assert member.session["roles"] == ["viewer"]


async def test_member_invite_sets_a_placeholder_credential_nobody_knows(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        roles = {r["key"]: r["id"] for r in (await owner.get("roles")).json()}
        email = f"{unique('member')}@example.com"
        created = await owner.create(
            "members",
            {"email": email, "display_name": "Member", "role_ids": [roles["viewer"]]},
        )
        assert created["invite_link"] is None  # the link goes to the mailbox only
    async with stack.browser() as anon:
        # Nobody can sign in until the invite is accepted; there is no password to guess.
        guess = await anon.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert guess.status_code == 401
        token = invite_token(email)
        accepted = await anon.post(
            "/api/v1/auth/accept-invite", json={"token": token, "new_password": PASSWORD}
        )
        assert accepted.status_code == 201 and accepted.json()["roles"] == ["viewer"]
        # Single-use.
        replay = await anon.post(
            "/api/v1/auth/accept-invite",
            json={"token": token, "new_password": "Another-One-99"},
        )
        assert replay.status_code == 422 and error_code(replay) == "INVALID_INVITE_TOKEN"


async def verify_email_in_db(stack, email):
    await db_execute(
        stack,
        update(PlatformUser)
        .where(PlatformUser.email == email)
        .values(email_verified_at=datetime.now(UTC)),
    )


async def invite(admin, email, role="viewer", name="Invitee"):
    roles = {r["key"]: r["id"] for r in (await admin.get("roles")).json()}
    return await admin.create(
        "members", {"email": email, "display_name": name, "role_ids": [roles[role]]}
    )


async def enrol_factors(stack, user_id):
    """What a squatter could have set up on the account before the real owner arrives."""
    await db_execute(
        stack,
        UserPasskey.__table__.insert().values(
            user_id=user_id,
            credential_id=f"cred-{uuid4().hex}",
            public_key=b"k",
            name="Squatter key",
        ),
    )
    await db_execute(
        stack,
        UserFace.__table__.insert().values(
            user_id=user_id, name="Squatter face", code_encrypted="x"
        ),
    )
    await db_execute(
        stack,
        update(UserCredential)
        .where(UserCredential.user_id == user_id)
        .values(second_factor_pin_hash=hash_password("482913")),
    )


async def count_rows(stack, model, *conditions):
    return await db_scalar(stack, select(func.count()).select_from(model).where(*conditions))


async def test_adding_a_verified_existing_user_as_a_member_never_touches_their_password(stack):
    # Verified accounts only: their mailbox is proven, so the plain "sign in" link is safe.
    # Unverified accounts are handled by the squatting tests below (SEC-1).
    async with stack.browser() as first, stack.browser() as second:
        alice = await stack.register(first)
        await verify_email_in_db(stack, alice.email)
        bob = await stack.register(second)
        created = await invite(bob, alice.email, name="Alice")
        assert created["invite_link"] is None
        assert (await first.get("/api/v1/auth/session")).status_code == 200  # her session lives
        # Active at once, no link needed.
        switched = await alice.switch(bob.tenant_id, bob.environment_id)
        assert switched["roles"] == ["viewer"]
    async with stack.browser() as browser:
        await stack.login(browser, alice.email)  # her original password still works


async def test_invite_to_a_squatted_address_gives_the_squatter_nothing_and_the_owner_everything(
    stack,
):
    new_password = "Mailbox-Owner-22"
    async with stack.browser() as squat_browser, stack.browser() as admin_browser:
        squatter = await stack.register(squat_browser)  # registers an address it does not own
        squat_id = squatter.session["user"]["id"]
        await enrol_factors(stack, squat_id)
        admin = await stack.register(admin_browser)
        mails_before = len(sent_to(squatter.email))  # the sign-up confirmation
        created = await invite(admin, squatter.email)

        # The admin gets no link and no token, so cannot take the account over.
        assert created["invite_link"] is None and "token" not in str(created).lower()
        assert len(sent_to(squatter.email)) == mails_before + 1  # the link went to the mailbox only

        # The squatter's credential is untouched but the roles are NOT usable: pending.
        assert (await squat_browser.get("/api/v1/auth/session")).status_code == 200
        denied = await squatter.put(
            "auth/session/workspace", {"tenant_id": admin.tenant_id, "environment_id": None}
        )
        assert denied.status_code == 404
        row = await db_scalar(
            stack,
            select(Membership.status).where(
                Membership.tenant_id == admin.tenant_id, Membership.user_id == squat_id
            ),
        )
        assert row == "revoked"  # pending: grants nothing anywhere
        squatter_cookies = dict(squat_browser.cookies)

    # The real owner of the mailbox follows the emailed link.
    async with stack.browser() as owner_browser:
        accepted = await owner_browser.post(
            "/api/v1/auth/accept-invite",
            json={"token": invite_token(squatter.email), "new_password": new_password},
        )
        assert accepted.status_code == 201, accepted.text
    # The squatter is cut off: session, password, passkey, face, PIN.
    async with stack.browser() as late:
        late.cookies.update(squatter_cookies)
        assert (await late.get("/api/v1/auth/session")).status_code == 401
        late.cookies.clear()
        old = await late.post(
            "/api/v1/auth/login", json={"email": squatter.email, "password": PASSWORD}
        )
        assert old.status_code == 401
    assert await count_rows(stack, UserPasskey, UserPasskey.user_id == squat_id) == 0
    assert await count_rows(stack, UserFace, UserFace.user_id == squat_id) == 0
    assert (
        await db_scalar(
            stack,
            select(UserCredential.second_factor_pin_hash).where(UserCredential.user_id == squat_id),
        )
        is None
    )
    assert await db_scalar(
        stack, select(PlatformUser.email_verified_at).where(PlatformUser.id == squat_id)
    )
    async with stack.browser() as real:
        actor = await stack.login(real, squatter.email, new_password)
        assert actor.session["user"]["id"] == squat_id
        switched = await actor.switch(admin.tenant_id, admin.environment_id)
        assert switched["roles"] == ["viewer"]
        # Single use.
        replay = await real.post(
            "/api/v1/auth/accept-invite",
            json={"token": invite_token(squatter.email), "new_password": "Other-Pass-33"},
        )
        assert replay.status_code == 422 and error_code(replay) == "INVALID_INVITE_TOKEN"

    # Audit: actor and tenant on the invite, target user id, no email or secret.
    event = (
        await stack.app.state.test_connection.execute(
            select(AuditEvent.actor_user_id, AuditEvent.tenant_id, AuditEvent.details).where(
                AuditEvent.action == "member.added", AuditEvent.tenant_id == admin.tenant_id
            )
        )
    ).first()
    assert str(event.actor_user_id) == admin.session["user"]["id"]
    assert event.details["user_id"] == squat_id and event.details["pending"] is True
    assert squatter.email not in str(event.details)
    assert await count_rows(
        stack,
        AuditEvent,
        AuditEvent.action == "auth.invite_accepted",
        AuditEvent.entity_id == squat_id,
    )


async def test_a_second_step_begun_before_the_takeover_is_void(stack):
    async with stack.browser() as squat_browser, stack.browser() as admin_browser:
        squatter = await stack.register(squat_browser)
        squat_id = squatter.session["user"]["id"]
        await enrol_factors(stack, squat_id)
        async with stack.browser() as step_one:
            ticket = (
                await step_one.post(
                    "/api/v1/auth/login", json={"email": squatter.email, "password": PASSWORD}
                )
            ).json()["ticket"]
        admin = await stack.register(admin_browser)
        await invite(admin, squatter.email)
    async with stack.browser() as owner:
        accepted = await owner.post(
            "/api/v1/auth/accept-invite",
            json={"token": invite_token(squatter.email), "new_password": "Owner-Pass-44"},
        )
        assert accepted.status_code == 201
    # Even if the squatter somehow still held a working factor, the old ticket is void.
    await db_execute(
        stack,
        update(UserCredential)
        .where(UserCredential.user_id == squat_id)
        .values(second_factor_pin_hash=hash_password("482913")),
    )
    async with stack.browser() as squat:
        finish = await squat.post("/api/v1/auth/mfa/pin", json={"ticket": ticket, "pin": "482913"})
        assert error_code(finish) == "SIGN_IN_EXPIRED"


async def test_invite_answers_look_the_same_for_new_unverified_and_verified_accounts(stack):
    async with stack.browser() as a, stack.browser() as b, stack.browser() as c:
        verified = await stack.register(a)
        await verify_email_in_db(stack, verified.email)
        unverified = await stack.register(b)
        admin = await stack.register(c)
        fresh = f"{unique('fresh')}@example.com"
        answers = [await invite(admin, e) for e in (verified.email, unverified.email, fresh)]
        assert len({tuple(sorted(x)) for x in answers}) == 1
        assert all(x["status"] == "active" and x["invite_link"] is None for x in answers)
        assert all(x["roles"] == ["viewer"] for x in answers)


async def test_two_pending_invites_activate_together_when_the_mailbox_owner_accepts(stack):
    async with stack.browser() as sq, stack.browser() as a, stack.browser() as b:
        squatter = await stack.register(sq)
        admin_a, admin_b = await stack.register(a), await stack.register(b)
        await invite(admin_a, squatter.email)
        await invite(admin_b, squatter.email, role="manager")
    async with stack.browser() as owner:
        accepted = await owner.post(
            "/api/v1/auth/accept-invite",
            json={"token": invite_token(squatter.email), "new_password": "Both-Pass-55"},
        )
        assert accepted.status_code == 201
    async with stack.browser() as real:
        actor = await stack.login(real, squatter.email, "Both-Pass-55")
        a_roles = (await actor.switch(admin_a.tenant_id, admin_a.environment_id))["roles"]
        b_roles = (await actor.switch(admin_b.tenant_id, admin_b.environment_id))["roles"]
        assert a_roles == ["viewer"] and b_roles == ["manager"]


async def test_a_refused_invite_changes_nothing(stack):
    async with stack.browser() as sq, stack.browser() as o, stack.browser() as v:
        squatter = await stack.register(sq)
        squat_id = squatter.session["user"]["id"]
        mails_before = len(sent_to(squatter.email))
        owner = await stack.register(o)
        viewer_email = await add_member(owner, ["viewer"])
        viewer = await stack.login(v, viewer_email)
        roles = {r["key"]: r["id"] for r in (await owner.get("roles")).json()}
        refused = await viewer.post(
            "members",
            {"email": squatter.email, "display_name": "X", "role_ids": [roles["viewer"]]},
        )
        assert refused.status_code == 403
    assert await count_rows(stack, Membership, Membership.user_id == squat_id) == 1  # own only
    assert await count_rows(stack, MemberInviteToken, MemberInviteToken.user_id == squat_id) == 0
    assert len(sent_to(squatter.email)) == mails_before  # no invitation went out
    async with stack.browser() as again:
        await stack.login(again, squatter.email)  # password untouched


async def test_an_admin_cancelling_a_pending_invite_kills_its_link(stack):
    async with stack.browser() as sq, stack.browser() as a:
        squatter = await stack.register(sq)
        admin = await stack.register(a)
        created = await invite(admin, squatter.email)
        assert (await admin.delete(f"members/{created['membership_id']}")).status_code == 204
    async with stack.browser() as owner:
        accepted = await owner.post(
            "/api/v1/auth/accept-invite",
            json={"token": invite_token(squatter.email), "new_password": "Late-Pass-66"},
        )
        assert accepted.status_code == 422 and error_code(accepted) == "INVALID_INVITE_TOKEN"


async def test_unverified_invitee_keeps_only_the_invited_workspace_roles(stack):
    # Scoping is unchanged: the invitee ends up a member of the inviting workspace with
    # exactly the granted role and nothing else, and their own workspace is untouched.
    async with stack.browser() as other, stack.browser() as admin_browser:
        invitee = await stack.register(other)
        admin = await stack.register(admin_browser)
        await invite(admin, invitee.email)
    async with stack.browser() as anon:
        accepted = await anon.post(
            "/api/v1/auth/accept-invite",
            json={"token": invite_token(invitee.email), "new_password": PASSWORD},
        )
        assert accepted.status_code == 201
    async with stack.browser() as again:
        actor = await stack.login(again, invitee.email)
        assert actor.session["roles"] == ["owner"]  # their own workspace is untouched
        switched = await actor.switch(admin.tenant_id, admin.environment_id)
        assert switched["roles"] == ["viewer"] and "customers.write" not in switched["permissions"]
