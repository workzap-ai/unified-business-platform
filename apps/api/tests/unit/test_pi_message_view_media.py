"""The team's thread shows what pi sent: the map picture, the board, a PDF, the buttons; and what
the customer sent and pi processed (with its saved file)."""

from datetime import UTC, datetime
from uuid import uuid4

from app.modules.pi.schemas import MessageView


def view(media, direction="outbound"):
    return MessageView.model_validate(
        {
            "id": uuid4(),
            "conversation_id": uuid4(),
            "direction": direction,
            "sender_type": "ai",
            "message_type": "image",
            "body": "caption",
            "media": media,
            "status": "sent",
            "error_code": None,
            "agent_key": None,
            "sent_by_label": None,
            "created_at": datetime.now(UTC),
        }
    )


def test_a_map_picture_pi_sent_shows_in_the_thread_with_its_alt_text() -> None:
    v = view(
        {
            "image": "https://api.example/brain-visuals/tok/map.png",
            "visual": "map",
            "alt": "Your problems: stock, cash",
            "map_version": 3,
            "buttons": [{"id": "a", "title": "Sahi hai"}, {"id": "b", "title": "Badlo"}],
        }
    )
    assert v.card == {"kind": "map", "image": "https://api.example/brain-visuals/tok/map.png"}
    assert v.media is not None
    assert v.media["visual"] == "map" and v.media["alt"].startswith("Your problems")
    assert v.media["buttons"] == ["Sahi hai", "Badlo"] and v.media["map_version"] == 3


def test_board_and_progress_pictures_show_too() -> None:
    for kind in ("board", "progress"):
        v = view({"image": "https://x.example/p.png", "visual": kind})
        assert v.card is not None and v.card["kind"] == kind


def test_a_pdf_pi_sent_shows_as_a_document_link() -> None:
    v = view({"document": {"link": "https://api.example/d/abc.pdf", "filename": "QUO-1.pdf"}})
    assert v.media == {
        "document": {"link": "https://api.example/d/abc.pdf", "filename": "QUO-1.pdf"}
    }


def test_a_customer_photo_keeps_its_reading_and_its_saved_file() -> None:
    v = view(
        {
            "mime_type": "image/jpeg",
            "size": 1200,
            "description": "A shop front",
            "file_id": "f1",
            "filename": "shop.jpg",
            "file_kind": "image",
            "media_url": "https://provider.example/secret",
            "provider_media_id": "wamid-1",
        },
        direction="inbound",
    )
    assert v.media is not None
    assert v.media["description"] == "A shop front" and v.media["file_id"] == "f1"
    assert "media_url" not in v.media and "provider_media_id" not in v.media


def test_unsafe_or_unknown_media_shows_nothing() -> None:
    assert view({"image": "javascript:alert(1)", "visual": "map"}).media is None
    assert view({"image": "https://x.example/a.png", "visual": "other"}).media is None
    assert view({"document": {"link": "file:///etc/passwd"}}).media is None
    assert view({"provider_media_id": "x", "mime_type": "image/png"}).media is None  # no size
    assert view(None).media is None
