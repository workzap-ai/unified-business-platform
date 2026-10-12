"""Quick-reply buttons: the reminder permission question goes out with [Yes] [No]
buttons, a tap is read as the title, and "Remind me later" pauses follow-ups."""

from datetime import UTC, datetime

import pytest
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import mock_turns, turn

from app.modules.pi.buttons import CONSENT, FOLLOW_UP, consent_buttons, is_remind_later

pytestmark = pytest.mark.integration


async def test_permission_question_has_buttons_and_remind_later_pauses(
    api, business_db, monkeypatch
):
    mock_turns(
        monkeypatch,
        turn(
            reply="Thanks, I've sent your brief to the team. The proposal comes here.",
            language="en",
            ready_for_team=True,
            awaiting_customer=False,
        ),
        turn(reply="Sure, I'll check back in two days.", language="en"),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("Yes please send it to the team", "confirm-1")
    await pi.deliver_all()
    [reply] = await pi.outbound()
    assert reply.media["buttons"] == CONSENT["en"]
    [payload] = pi.sent
    assert payload["type"] == "interactive"
    titles = [b["reply"]["title"] for b in payload["interactive"]["action"]["buttons"]]
    assert titles == ["Yes, message me", "No thanks"]

    await pi.process("Remind me later", "later-1")
    await pi.deliver_all()
    conversation = await pi.conversation()
    until = datetime.fromisoformat(conversation.service_brief["customer_waiting_until"])
    assert (until - datetime.now(UTC)).days >= 1
    await pi.close()


def test_button_titles_fit_whatsapp_and_are_recognised():
    for titles in (*CONSENT.values(), *FOLLOW_UP.values()):
        assert len(titles) <= 3 and all(len(t) <= 20 for t in titles)
    assert is_remind_later("Remind me later") and is_remind_later("Baad mein yaad dilao")
    assert not is_remind_later("later I will send the PDF")
    assert consent_buttons("Noted.") is None
