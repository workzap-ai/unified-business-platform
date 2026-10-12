"""pi hands off rarely. Stickers are skipped, a file it can't open gets a polite ask and
a request for the team, a reply that makes things up (a "[Google Meet Link]", a meeting
"confirmed" that nobody booked) is never sent, and the chat stays with pi."""

import pytest
from sqlalchemy import select
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import mock_turns, turn

from app.modules.pi.whatsapp import other_text
from app.modules.pi_saas.models import PiStaffRequest

pytestmark = pytest.mark.integration


def test_buttons_locations_and_contacts_become_words():
    assert other_text("button", {"button": {"text": "Yes, send it"}}) == "Yes, send it"
    where = other_text(
        "location",
        {"location": {"latitude": 31.5, "longitude": 74.3, "name": "Office", "address": "Gulberg"}},
    )
    assert where.startswith("Location shared: Office, Gulberg") and "31.5" in where
    card = other_text(
        "contacts",
        {"contacts": [{"name": {"formatted_name": "Ali"}, "phones": [{"phone": "+923001"}]}]},
    )
    assert card == "Contact card shared: Ali +923001"
    assert other_text("sticker", {"sticker": {"id": "1"}}) == ""


async def test_a_sticker_is_skipped_quietly(api, business_db):
    pi = await pi_workspace(api, business_db)
    await pi.process("", "rare-sticker", kind="sticker", media_id="1234567")
    conversation = await pi.conversation()
    assert conversation.mode == "ai" and await pi.outbound() == []
    await pi.close()


async def test_a_file_pi_cannot_open_keeps_the_chat(api, business_db):
    pi = await pi_workspace(api, business_db)  # image understanding isn't switched on here
    await pi.process("see this", "rare-image", kind="image", media_id="7654321")
    conversation = await pi.conversation()
    assert conversation.mode == "ai"
    [notice] = await pi.outbound()
    assert "couldn't open that file" in notice.body
    [request] = list(
        await business_db.scalars(
            select(PiStaffRequest).where(PiStaffRequest.conversation_id == conversation.id)
        )
    )
    assert request.kind == "review_document"
    await pi.close()


async def test_a_made_up_meeting_link_is_never_sent(api, business_db, monkeypatch):
    mock_turns(
        monkeypatch,
        turn(
            reply="Your meeting is confirmed for five PM. Link: [Google Meet Link]",
            meeting_requested=True,
        ),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("google meet meeting link?", "rare-link")
    conversation = await pi.conversation()
    assert conversation.mode == "ai"
    bodies = [m.body for m in await pi.outbound()]
    assert not any("[Google Meet Link]" in b or "confirmed" in b for b in bodies)
    assert any("checking this with the team" in b for b in bodies)
    kinds = set(
        await business_db.scalars(
            select(PiStaffRequest.kind).where(PiStaffRequest.conversation_id == conversation.id)
        )
    )
    assert kinds & {"question", "meeting"}
    await pi.close()
