"""A computer without Windows Hello: after the password, a 6-digit code sent to the
account's email is the second step. Never without the password, wrong codes count
toward the same lock, and a code works once."""

import pytest
from test_face_sign_in import PASSWORD, _browser, _password
from test_passkeys import Authenticator
from test_service_lifecycle import register

from app.modules.auth import mfa

pytestmark = pytest.mark.integration


@pytest.fixture
def mailbox(api, monkeypatch):
    settings = api._transport.app.state.settings  # type: ignore[attr-defined]
    monkeypatch.setattr(settings, "platform_smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "platform_smtp_from", "no-reply@example.test")
    sent: list[dict] = []

    async def fake_send(settings, http, template, to, variables, **kwargs):
        sent.append({"template": template, "to": list(to), **variables})

    monkeypatch.setattr(mfa, "send_platform_template", fake_send)
    return sent


async def test_email_code_is_a_second_step_for_any_computer(api, mailbox):
    me = await register(api)
    device = Authenticator()
    options = (
        await api.post("/api/v1/auth/passkeys/register/options", json={"password": PASSWORD})
    ).json()
    added = await api.post(
        "/api/v1/auth/passkeys/register/verify",
        json={"credential": device.create(options), "name": "Phone"},
    )
    assert added.status_code == 201, added.text

    browser = _browser(api)
    step = await _password(browser, me["user"]["email"])
    assert step["methods"] == ["fingerprint", "email"]
    started = await browser.post("/api/v1/auth/mfa/email/start", json={"ticket": step["ticket"]})
    assert started.status_code == 200, started.text
    assert "@" in started.json()["sent_to"] and me["user"]["email"] not in started.text
    [mail] = mailbox
    assert mail["template"] == "sign_in_code" and mail["to"] == [me["user"]["email"]]
    code = mail["code"]
    assert len(code) == 6 and code.isdigit()

    wrong = "000000" if code != "000000" else "111111"
    bad = await browser.post(
        "/api/v1/auth/mfa/email", json={"ticket": step["ticket"], "code": wrong}
    )
    assert bad.status_code == 401 and "4 tries left" in bad.json()["error"]["message"]
    ok = await browser.post("/api/v1/auth/mfa/email", json={"ticket": step["ticket"], "code": code})
    assert ok.status_code == 200, ok.text
    again = await browser.post(
        "/api/v1/auth/mfa/email", json={"ticket": step["ticket"], "code": code}
    )
    assert again.status_code in (400, 410, 422)  # the code and ticket were used up
    await browser.aclose()


async def test_no_email_code_when_the_platform_cannot_send(api):
    me = await register(api)
    device = Authenticator()
    options = (
        await api.post("/api/v1/auth/passkeys/register/options", json={"password": PASSWORD})
    ).json()
    await api.post(
        "/api/v1/auth/passkeys/register/verify",
        json={"credential": device.create(options), "name": "Phone"},
    )
    browser = _browser(api)
    step = await _password(browser, me["user"]["email"])
    assert step["methods"] == ["fingerprint"]
    await browser.aclose()
