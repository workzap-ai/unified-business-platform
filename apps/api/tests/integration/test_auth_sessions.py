"""Authentication, sessions, CSRF and origin checks through the real HTTP stack."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.modules.auth.crypto import digest
from app.modules.auth.models import AuthSession, UserCredential
from app.modules.users.models import PlatformUser
from tests.support.workspace import PASSWORD, add_member, error_code, unique

pytestmark = pytest.mark.integration


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


async def test_member_created_with_initial_password_can_sign_in_and_existing_is_untouched(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        email = await add_member(owner, ["viewer"], password="Initial-Secret-42")
    async with stack.browser() as browser:
        member = await stack.login(browser, email, "Initial-Secret-42")
        assert member.session["roles"] == ["viewer"]
