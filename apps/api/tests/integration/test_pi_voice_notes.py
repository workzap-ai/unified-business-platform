"""Kapso voice notes: Pi uses Kapso's transcript and file link, so a voice note gets an
AI reply instead of "a member of our team will review it"."""

import httpx
import pytest
from pi_saas_support import FakeProvider, configure
from sqlalchemy import select
from test_pi_saas import _is_read_receipt, _kapso, _ready_business, _run_jobs
from test_pi_service_conversations import mock_turns, turn

from app.ai.manager import LLMManager
from app.modules.pi.models import PiConversation, PiMessage

pytestmark = pytest.mark.integration

AUDIO = b"OggS" + b"\x00" * 64
FILE_URL = "https://app.kapso.ai/rails/active_storage/blobs/voice.ogg"


@pytest.fixture
def app(api):
    return api._transport.app  # type: ignore[attr-defined]


@pytest.fixture
def provider(app):
    fake = FakeProvider()
    fake.queue = configure(app, fake)  # type: ignore[attr-defined]
    return fake


def _voice_event(number: str, sender: str, mid: str, transcript: str = "") -> dict:
    kapso: dict = {"media_url": FILE_URL, "media_data": {"content_type": "audio/ogg; codecs=opus"}}
    if transcript:
        kapso["transcript"] = {"text": transcript}
    return {
        "message": {
            "id": mid,
            "timestamp": "1730092800",
            "type": "audio",
            "from": sender,
            "audio": {"id": "1234567890123", "mime_type": "audio/ogg; codecs=opus"},
            "kapso": kapso,
        },
        "conversation": {"id": "conv_v", "phone_number": sender, "phone_number_id": number},
        "phone_number_id": number,
    }


def _serve_file(app, provider, *, available: bool) -> list[str]:
    """Kapso's file host on top of the fake provider; records what was fetched."""
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "app.kapso.ai":
            fetched.append(str(request.url))
            return httpx.Response(200, content=AUDIO) if available else httpx.Response(404)
        return provider(request)

    app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return fetched


def _no_transcription(monkeypatch) -> list[bytes]:
    calls: list[bytes] = []

    async def transcribe(self, scope, data, mime, **kwargs):
        calls.append(data)
        raise AssertionError("Kapso already transcribed this voice note")

    monkeypatch.setattr(LLMManager, "transcribe", transcribe)
    return calls


async def _inbound(db, mid: str) -> PiMessage:
    row = await db.scalar(select(PiMessage).where(PiMessage.provider_message_id == mid))
    assert row is not None
    return row


async def test_voice_note_uses_kapso_transcript_and_file(app, provider, business_db, monkeypatch):
    contexts = mock_turns(monkeypatch, turn(reply="Ji, website ke liye kuch sawal hain."))
    transcribed = _no_transcription(monkeypatch)
    client, _ = await _ready_business(app, provider, business_db, "Voice", "6100000001")
    fetched = _serve_file(app, provider, available=True)
    await _kapso(
        client,
        "whatsapp.message.received",
        _voice_event("6100000001", "15550006101", "wamid.v1", "Mujhe website banwani hai"),
    )
    await _run_jobs(app, provider, business_db)
    assert fetched == [FILE_URL] and transcribed == []
    assert "Mujhe website banwani hai" in contexts[0]
    inbound = await _inbound(business_db, "wamid.v1")
    assert inbound.media["transcript"] == "Mujhe website banwani hai"
    assert inbound.media["size"] == len(AUDIO) and inbound.media["mime_type"] == "audio/ogg"
    conversation = await business_db.get(PiConversation, inbound.conversation_id)
    assert conversation.mode == "ai"
    sends = [
        r for r in provider.requests if r.url.path.endswith("/messages") and not _is_read_receipt(r)
    ]
    assert len(sends) == 1 and b"website ke liye" in sends[0].content
    # The team can play the voice note in the inbox; another business cannot.
    path = f"/api/v1/pi-app/pi/conversations/{conversation.id}/messages/{inbound.id}/media"
    played = await client.get(path)
    assert played.status_code == 200 and played.content == AUDIO
    assert played.headers["content-type"] == "audio/ogg"
    other, _ = await _ready_business(app, provider, business_db, "Other", "6100000009")
    assert (await other.get(path)).status_code == 404
    await other.aclose()
    await client.aclose()


async def test_voice_note_is_answered_even_when_the_file_cannot_be_fetched(
    app, provider, business_db, monkeypatch
):
    contexts = mock_turns(monkeypatch, turn())
    _no_transcription(monkeypatch)
    client, _ = await _ready_business(app, provider, business_db, "Voice2", "6100000002")
    _serve_file(app, provider, available=False)
    await _kapso(
        client,
        "whatsapp.message.received",
        _voice_event("6100000002", "15550006102", "wamid.v2", "Logo bhi chahiye"),
    )
    await _run_jobs(app, provider, business_db)
    assert "Logo bhi chahiye" in contexts[0]
    inbound = await _inbound(business_db, "wamid.v2")
    assert inbound.media["transcript"] == "Logo bhi chahiye"
    conversation = await business_db.get(PiConversation, inbound.conversation_id)
    assert conversation.mode == "ai"
    await client.aclose()


async def test_voice_note_without_any_transcript_still_goes_to_the_team(
    app, provider, business_db, monkeypatch
):
    mock_turns(monkeypatch)
    _no_transcription(monkeypatch)
    client, _ = await _ready_business(app, provider, business_db, "Voice3", "6100000003")
    _serve_file(app, provider, available=False)
    await _kapso(
        client, "whatsapp.message.received", _voice_event("6100000003", "15550006103", "wamid.v3")
    )
    await _run_jobs(app, provider, business_db)
    inbound = await _inbound(business_db, "wamid.v3")
    conversation = await business_db.get(PiConversation, inbound.conversation_id)
    assert conversation.mode == "human"
    await client.aclose()
