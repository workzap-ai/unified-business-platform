"""An optional sign-in PIN: set with the person's own password, asked after the
password (never instead of it), wrong PINs count toward the same lock, and simple
runs like 123456 are refused."""

import pytest
from test_face_sign_in import PASSWORD, _browser, _password
from test_service_lifecycle import register

pytestmark = pytest.mark.integration


async def test_pin_is_a_second_step_after_the_password(api):
    me = await register(api)
    assert (await api.get("/api/v1/auth/pin")).json() == {"set": False}
    browser = _browser(api)
    plain = await _password(browser, me["user"]["email"])
    assert plain.get("mfa_required") is not True  # no PIN yet: the password signs in

    wrong_password = await api.put("/api/v1/auth/pin", json={"password": "nope", "pin": "482913"})
    assert wrong_password.status_code == 403
    simple = await api.put("/api/v1/auth/pin", json={"password": PASSWORD, "pin": "123456"})
    assert simple.status_code == 422
    saved = await api.put("/api/v1/auth/pin", json={"password": PASSWORD, "pin": "482913"})
    assert saved.status_code == 200 and saved.json() == {"set": True}

    step = await _password(browser, me["user"]["email"])
    assert step["mfa_required"] is True and "pin" in step["methods"]
    bad = await browser.post(
        "/api/v1/auth/mfa/pin", json={"ticket": step["ticket"], "pin": "000111"}
    )
    assert bad.status_code == 401 and "4 tries left" in bad.json()["error"]["message"]
    ok = await browser.post(
        "/api/v1/auth/mfa/pin", json={"ticket": step["ticket"], "pin": "482913"}
    )
    assert ok.status_code == 200, ok.text

    removed = await api.post("/api/v1/auth/pin/remove", json={"password": PASSWORD})
    assert removed.json() == {"set": False}
    again = await _password(browser, me["user"]["email"])
    assert again.get("mfa_required") is not True
    await browser.aclose()
