"""Passkeys (Face ID / Touch ID / Windows Hello) end to end with a software authenticator
that signs real WebAuthn responses: add needs the password, sign-in issues a session,
challenges are single use, other sites and replayed or forged responses are refused."""

import hashlib
import json
import os
import struct
from base64 import urlsafe_b64decode, urlsafe_b64encode
from uuid import UUID

import cbor2
import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import func, select
from test_service_lifecycle import register

from app.modules.audit.models import AuditEvent

pytestmark = pytest.mark.integration

ORIGIN = "http://localhost:3000"
RP_ID = "localhost"
PASSWORD = "ServiceFlow!Secure234"


def b64(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode()


class Authenticator:
    """A device that holds one passkey and always 'recognises the face' (UV)."""

    def __init__(self) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.count = 0
        self.user_handle = b""

    def _client_data(self, kind: str, challenge: str, origin: str) -> bytes:
        return json.dumps({"type": kind, "challenge": challenge, "origin": origin}).encode()

    def create(self, options: dict, origin: str = ORIGIN, rp_id: str = RP_ID) -> dict:
        numbers = self.key.public_key().public_numbers()
        cose = cbor2.dumps(
            {
                1: 2,
                3: -7,
                -1: 1,
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )
        auth_data = (
            hashlib.sha256(rp_id.encode()).digest()
            + bytes([0x01 | 0x04 | 0x40])  # user present, user verified, attested data
            + struct.pack(">I", self.count)
            + bytes(16)
            + struct.pack(">H", len(self.credential_id))
            + self.credential_id
            + cose
        )
        self.user_handle = _unb64(options["user"]["id"])
        return {
            "id": b64(self.credential_id),
            "rawId": b64(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64(
                    self._client_data("webauthn.create", options["challenge"], origin)
                ),
                "attestationObject": b64(
                    cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
                ),
                "transports": ["internal"],
            },
            "clientExtensionResults": {},
        }

    def get(self, options: dict, origin: str = ORIGIN, *, verified: bool = True) -> dict:
        self.count += 1
        flags = 0x01 | (0x04 if verified else 0)
        auth_data = (
            hashlib.sha256(RP_ID.encode()).digest() + bytes([flags]) + struct.pack(">I", self.count)
        )
        client = self._client_data("webauthn.get", options["challenge"], origin)
        signature = self.key.sign(
            auth_data + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "id": b64(self.credential_id),
            "rawId": b64(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64(client),
                "authenticatorData": b64(auth_data),
                "signature": b64(signature),
                "userHandle": b64(self.user_handle),
            },
            "clientExtensionResults": {},
        }


def _unb64(value: str) -> bytes:
    return urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _anon(api, origin: str = ORIGIN) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api._transport.app),  # type: ignore[attr-defined]
        base_url="http://testserver",
        headers={"origin": origin},
    )


async def _add(api, device: Authenticator) -> dict:
    options = (
        await api.post("/api/v1/auth/passkeys/register/options", json={"password": PASSWORD})
    ).json()
    added = await api.post(
        "/api/v1/auth/passkeys/register/verify",
        json={"credential": device.create(options), "name": "Sana's iPhone"},
    )
    assert added.status_code == 201, added.text
    return added.json()


async def _ticket(client: httpx.AsyncClient, email: str) -> str:
    step = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert step.status_code == 200 and step.json()["mfa_required"], step.text
    return step.json()["ticket"]


async def _challenge(client: httpx.AsyncClient, ticket: str) -> dict:
    options = await client.post("/api/v1/auth/mfa/fingerprint/options", json={"ticket": ticket})
    assert options.status_code == 200, options.text
    return options.json()["options"]


async def _login(client: httpx.AsyncClient, email: str, device: Authenticator, **kw):
    """Owner OS: the password first, then the fingerprint (passkey) as the second step."""
    ticket = await _ticket(client, email)
    options = await _challenge(client, ticket)
    assert options["userVerification"] == "required"
    return await client.post(
        "/api/v1/auth/mfa/fingerprint",
        json={"ticket": ticket, "credential": device.get(options, **kw)},
    )


async def test_add_passkey_then_sign_in_with_password_and_fingerprint(api, business_db):
    me = await register(api)
    wrong = await api.post(
        "/api/v1/auth/passkeys/register/options", json={"password": "not-my-password"}
    )
    assert wrong.status_code == 403
    options = (
        await api.post("/api/v1/auth/passkeys/register/options", json={"password": PASSWORD})
    ).json()
    assert options["rp"]["id"] == RP_ID
    assert options["authenticatorSelection"]["userVerification"] == "required"
    assert options["authenticatorSelection"]["residentKey"] == "required"

    device = Authenticator()
    added = await api.post(
        "/api/v1/auth/passkeys/register/verify",
        json={"credential": device.create(options), "name": "Sana's iPhone"},
    )
    assert added.status_code == 201, added.text
    again = await api.post(
        "/api/v1/auth/passkeys/register/verify",
        json={"credential": device.create(options)},
    )
    assert again.status_code == 422  # the challenge was single use
    listed = (await api.get("/api/v1/auth/passkeys")).json()
    assert [p["name"] for p in listed] == ["Sana's iPhone"]

    browser = _anon(api)
    signed_in = await _login(browser, me["user"]["email"], device)
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json()["user"]["email"] == me["user"]["email"]
    assert (await browser.get("/api/v1/auth/session")).status_code == 200
    used = (await api.get("/api/v1/auth/passkeys")).json()[0]
    assert used["last_used_at"] is not None
    audited = await business_db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.action.in_(["auth.passkey_added", "auth.login"]))
        .where(AuditEvent.actor_user_id == UUID(me["user"]["id"]))
    )
    assert audited == 2  # passkey added, then the password + fingerprint sign-in
    await browser.aclose()


async def test_refuses_other_sites_replays_and_unverified_fingerprints(api):
    me = await register(api)
    email = me["user"]["email"]
    device = Authenticator()
    await _add(api, device)

    browser = _anon(api)
    # A response signed for another website is rejected even with a valid challenge.
    ticket = await _ticket(browser, email)
    phished = await browser.post(
        "/api/v1/auth/mfa/fingerprint",
        json={
            "ticket": ticket,
            "credential": device.get(
                await _challenge(browser, ticket), origin="https://evil.example"
            ),
        },
    )
    assert phished.status_code == 401
    # The fingerprint/PIN wasn't checked by the device: refused.
    assert (await _login(browser, email, device, verified=False)).status_code == 401
    # Replaying a used sign-in fails.
    ticket = await _ticket(browser, email)
    credential = device.get(await _challenge(browser, ticket))
    ok = await browser.post(
        "/api/v1/auth/mfa/fingerprint", json={"ticket": ticket, "credential": credential}
    )
    assert ok.status_code == 200
    replay = await browser.post(
        "/api/v1/auth/mfa/fingerprint", json={"ticket": ticket, "credential": credential}
    )
    assert replay.status_code == 422
    # A different device (unknown passkey) can't finish the sign-in.
    assert (await _login(browser, email, Authenticator())).status_code == 401
    await browser.aclose()


async def test_remove_and_rename_only_your_own(api):
    me = await register(api)
    device = Authenticator()
    mine = await _add(api, device)
    renamed = await api.patch(f"/api/v1/auth/passkeys/{mine['id']}", json={"name": "Work Mac"})
    assert renamed.json()["name"] == "Work Mac"

    other = _anon(api)
    await register(other)
    assert (await other.delete(f"/api/v1/auth/passkeys/{mine['id']}")).status_code == 404
    assert (await api.delete(f"/api/v1/auth/passkeys/{mine['id']}")).status_code == 204
    assert (await api.get("/api/v1/auth/passkeys")).json() == []
    # With nothing saved, the password signs in on its own again.
    browser = _anon(api)
    plain = await browser.post(
        "/api/v1/auth/login", json={"email": me["user"]["email"], "password": PASSWORD}
    )
    assert plain.status_code == 200 and "mfa_required" not in plain.json()
    await other.aclose()
    await browser.aclose()


# ---- pi app ---------------------------------------------------------------------------


PI_ORIGIN = "http://localhost:3200"


async def test_pi_app_adds_a_passkey_but_never_signs_in_with_it_alone(api):
    from pi_saas_support import PASSWORD as PI_PASSWORD
    from pi_saas_support import pi_client, pi_register

    client = pi_client(api._transport.app)  # type: ignore[attr-defined]
    await pi_register(client)
    client.headers["x-csrf-token"] = client.cookies["pi_csrf"]
    base = "/api/v1/pi-app/auth/passkeys"
    options = (await client.post(f"{base}/register/options", json={"password": PI_PASSWORD})).json()
    assert options["rp"]["name"] == "pi"
    added = await client.post(
        f"{base}/register/verify",
        json={"credential": Authenticator().create(options, origin=PI_ORIGIN)},
    )
    assert added.status_code == 201, added.text
    alone = await _anon(api, PI_ORIGIN).post(f"{base}/login/options")
    assert alone.status_code in (404, 405)  # a passkey is never a sign-in on its own
    await client.aclose()
