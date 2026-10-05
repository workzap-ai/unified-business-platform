"""Owner OS two-step sign-in: password, then the face (real camera frames run through the
real face engine) or an optional fingerprint (passkey). Up to three faces, only the
signed-in person's password opens the camera step, the password alone never signs in
someone who saved a face, and wrong tries lock the step (counted in the database,
back to zero after success)."""

import base64
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import cv2
import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select, update
from test_passkeys import Authenticator
from test_service_lifecycle import register

from app.modules.auth import face as face_engine
from app.modules.auth.models import UserCredential, UserFace

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "faces"
PASSWORD = "ServiceFlow!Secure234"
ORIGIN = "http://localhost:3000"


def frames(name: str = "astronaut.jpg", *, grow: bool = True) -> list[str]:
    """Three camera frames: the person moves a little closer (the picture zooms)."""
    image = cv2.imread(str(FIXTURES / name))
    h, w = image.shape[:2]
    out = []
    for step, zoom in enumerate((1.0, 1.08, 1.18) if grow else (1.0, 1.0, 1.0)):
        cw, ch = int(w / zoom), int(h / zoom)
        x, y = (w - cw) // 2, (h - ch) // 3
        crop = cv2.resize(image[y : y + ch, x : x + cw], (w, h))
        crop = cv2.convertScaleAbs(crop, alpha=1.0, beta=step * 3)  # never byte-identical
        ok, jpeg = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        assert ok
        out.append(base64.b64encode(jpeg.tobytes()).decode())
    return out


@pytest.fixture(autouse=True)
def encryption(api):
    settings = api._transport.app.state.settings  # type: ignore[attr-defined]
    if settings.secrets_encryption_key is None:
        settings.secrets_encryption_key = SecretStr(Fernet.generate_key().decode())


def _browser(api) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api._transport.app),  # type: ignore[attr-defined]
        base_url="http://testserver",
        headers={"origin": ORIGIN},
    )


async def _add_face(api, name: str = "") -> httpx.Response:
    started = await api.post("/api/v1/auth/faces/start", json={"password": PASSWORD})
    assert started.status_code == 200, started.text
    return await api.post(
        "/api/v1/auth/faces",
        json={"ticket": started.json()["ticket"], "name": name, "frames": frames()},
    )


async def _password(browser: httpx.AsyncClient, email: str) -> dict:
    response = await browser.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


async def test_face_engine_matches_the_same_person_and_needs_a_live_face():
    found = face_engine.live_frames(face_engine.decode_frames(frames()))
    code = face_engine.face_code(found)
    assert face_engine.similarity(found, code) > 0.8
    with pytest.raises(face_engine.FaceError) as still:
        face_engine.live_frames(face_engine.decode_frames(frames(grow=False)))
    assert still.value.code == "FACE_NOT_LIVE"  # didn't move closer: looks like a photo
    same = frames()[0]
    with pytest.raises(face_engine.FaceError):
        face_engine.live_frames(face_engine.decode_frames([same, same, same]))
    with pytest.raises(face_engine.FaceError) as nobody:
        face_engine.live_frames(face_engine.decode_frames(frames("no-face.jpg")))
    assert nobody.value.code == "FACE_NOT_FOUND"


async def test_password_then_face_signs_in_and_password_alone_does_not(api, business_db):
    me = await register(api)
    email = me["user"]["email"]
    wrong = await api.post("/api/v1/auth/faces/start", json={"password": "not-it"})
    assert wrong.status_code == 403  # only your own password opens the camera
    added = await _add_face(api, "Office camera")
    assert added.status_code == 201, added.text
    saved = await business_db.scalar(
        select(UserFace).where(UserFace.id == UUID(added.json()["id"]))
    )
    assert saved is not None and "astronaut" not in saved.code_encrypted  # encrypted code only

    browser = _browser(api)
    step = await _password(browser, email)
    assert step["mfa_required"] is True and step["methods"] == ["face"]
    assert (await browser.get("/api/v1/auth/session")).status_code == 401  # not signed in yet
    signed_in = await browser.post(
        "/api/v1/auth/mfa/face", json={"ticket": step["ticket"], "frames": frames()}
    )
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json()["user"]["email"] == email
    assert (await browser.get("/api/v1/auth/session")).status_code == 200
    reused = await browser.post(
        "/api/v1/auth/mfa/face", json={"ticket": step["ticket"], "frames": frames()}
    )
    assert reused.status_code == 422  # the ticket is single use
    listed = (await api.get("/api/v1/auth/faces")).json()
    assert listed["max"] == 3 and listed["faces"][0]["last_used_at"] is not None
    await browser.aclose()


async def test_three_faces_at_most_and_only_your_own(api):
    await register(api)
    for n in range(3):
        assert (await _add_face(api, f"Face {n + 1}")).status_code == 201
    fourth = await api.post("/api/v1/auth/faces/start", json={"password": PASSWORD})
    assert fourth.status_code == 422 and fourth.json()["error"]["code"] == "TOO_MANY_FACES"
    mine = (await api.get("/api/v1/auth/faces")).json()["faces"]
    other = _browser(api)
    await register(other)
    assert (await other.delete(f"/api/v1/auth/faces/{mine[0]['id']}")).status_code == 404
    assert (await api.delete(f"/api/v1/auth/faces/{mine[0]['id']}")).status_code == 204
    assert (await _add_face(api)).status_code == 201  # room again
    await other.aclose()


async def test_wrong_faces_lock_the_step_and_success_resets_the_count(
    api, business_db, monkeypatch
):
    me = await register(api)
    email, user_id = me["user"]["email"], UUID(me["user"]["id"])
    assert (await _add_face(api)).status_code == 201
    browser = _browser(api)

    # No face in the picture: a camera problem, not a wrong try.
    step = await _password(browser, email)
    nobody = await browser.post(
        "/api/v1/auth/mfa/face", json={"ticket": step["ticket"], "frames": frames("no-face.jpg")}
    )
    assert nobody.status_code == 422 and nobody.json()["error"]["code"] == "FACE_NOT_FOUND"
    credential = await business_db.scalar(
        select(UserCredential).where(UserCredential.user_id == user_id)
    )
    assert credential.second_factor_failures == 0

    # A held-up photo (no movement) counts.
    still = await browser.post(
        "/api/v1/auth/mfa/face", json={"ticket": step["ticket"], "frames": frames(grow=False)}
    )
    assert still.status_code == 401 and "4 tries left" in still.json()["error"]["message"]

    # Someone else's face (simulated): wrong tries until the step locks.
    monkeypatch.setattr(face_engine, "similarity", lambda found, code: 0.1)
    for left in (3, 2, 1):
        miss = await browser.post(
            "/api/v1/auth/mfa/face", json={"ticket": step["ticket"], "frames": frames()}
        )
        assert miss.status_code == 401 and f"{left} tr" in miss.json()["error"]["message"]
    locked = await browser.post(
        "/api/v1/auth/mfa/face", json={"ticket": step["ticket"], "frames": frames()}
    )
    assert locked.status_code == 423
    await business_db.refresh(credential)
    assert credential.second_factor_locked_until is not None
    assert credential.second_factor_failures == 0  # counted in the database, then reset

    # Still locked even with the right password and a new ticket.
    monkeypatch.undo()
    step = await _password(browser, email)
    blocked = await browser.post(
        "/api/v1/auth/mfa/face", json={"ticket": step["ticket"], "frames": frames()}
    )
    assert blocked.status_code == 423
    # After the lock time passes the right face works and the count is back to zero.
    await business_db.execute(
        update(UserCredential)
        .where(UserCredential.user_id == user_id)
        .values(second_factor_locked_until=datetime.now(UTC) - timedelta(minutes=1))
    )
    ok = await browser.post(
        "/api/v1/auth/mfa/face", json={"ticket": step["ticket"], "frames": frames()}
    )
    assert ok.status_code == 200, ok.text
    await business_db.refresh(credential)
    assert credential.second_factor_failures == 0
    assert credential.second_factor_locked_until is None
    await browser.aclose()


async def test_optional_fingerprint_after_the_password_never_alone(api):
    me = await register(api)
    device = Authenticator()
    options = (
        await api.post("/api/v1/auth/passkeys/register/options", json={"password": PASSWORD})
    ).json()
    added = await api.post(
        "/api/v1/auth/passkeys/register/verify",
        json={"credential": device.create(options), "name": "Laptop fingerprint"},
    )
    assert added.status_code == 201, added.text

    browser = _browser(api)
    # There is no way to sign in to Owner OS with the fingerprint alone.
    alone = await browser.post("/api/v1/auth/passkeys/login/options")
    assert alone.status_code in (404, 405)
    step = await _password(browser, me["user"]["email"])
    assert step["methods"] == ["fingerprint"]
    challenge = (
        await browser.post("/api/v1/auth/mfa/fingerprint/options", json={"ticket": step["ticket"]})
    ).json()["options"]
    assert challenge["allowCredentials"] and challenge["userVerification"] == "required"
    # Fingerprint not actually checked by the device: refused and counted.
    lazy = await browser.post(
        "/api/v1/auth/mfa/fingerprint",
        json={"ticket": step["ticket"], "credential": device.get(challenge, verified=False)},
    )
    assert lazy.status_code in (401, 422)
    challenge = (
        await browser.post("/api/v1/auth/mfa/fingerprint/options", json={"ticket": step["ticket"]})
    ).json()["options"]
    signed_in = await browser.post(
        "/api/v1/auth/mfa/fingerprint",
        json={"ticket": step["ticket"], "credential": device.get(challenge)},
    )
    assert signed_in.status_code == 200, signed_in.text
    assert (await browser.get("/api/v1/auth/session")).status_code == 200
    await browser.aclose()


async def test_people_without_a_face_or_fingerprint_sign_in_as_before(api):
    me = await register(api)
    browser = _browser(api)
    plain = await browser.post(
        "/api/v1/auth/login", json={"email": me["user"]["email"], "password": PASSWORD}
    )
    assert plain.status_code == 200 and plain.json()["user"]["email"] == me["user"]["email"]
    await browser.aclose()
