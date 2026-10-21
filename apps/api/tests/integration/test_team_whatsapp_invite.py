"""Invites on WhatsApp: sent from the business's pi number when the person has an open
chat with it; otherwise a ready wa.me message for the inviter. Only invite and sign-in
links can be sent."""

import pytest
from test_pi_pipeline import pi_workspace

pytestmark = pytest.mark.integration
INVITE = "/api/v1/team-invites/whatsapp"
LINK = "http://localhost:3000/accept-invite?token=abc123"


async def test_invite_without_a_chat_gives_a_ready_whatsapp_message(api, business_db):
    pi = await pi_workspace(api, business_db)
    sent = await api.post(
        INVITE, json={"phone": "+92 300 1234567", "name": "Sara Khan", "link": LINK}
    )
    assert sent.status_code == 200, sent.text
    body = sent.json()
    assert body["delivery"] == "manual"
    assert body["share"].startswith("https://wa.me/923001234567?text=")
    assert "Hi Sara," in body["message"] and LINK in body["message"]
    await pi.close()


async def test_invite_goes_from_the_pi_number_when_the_chat_is_open(api, business_db):
    pi = await pi_workspace(api, business_db)
    await pi.process("hello", "wamid.team-1", sender="15550000009")
    sent = await api.post(INVITE, json={"phone": "+1 555 000 0009", "link": LINK})
    assert sent.status_code == 200, sent.text
    assert sent.json()["delivery"] == "sent"
    assert any(LINK in m.body for m in await pi.outbound())
    await pi.close()


async def test_only_invite_links_can_be_sent(api, business_db):
    pi = await pi_workspace(api, business_db)
    bad = await api.post(INVITE, json={"phone": "+923001234567", "link": "https://evil.example/x"})
    assert bad.status_code == 422
    await pi.close()
