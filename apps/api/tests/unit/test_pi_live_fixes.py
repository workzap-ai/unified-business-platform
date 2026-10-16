"""Fixes from watching live chats (16 Oct): handoffs only on request, no repeats, real
account answers, media models that exist, every customer file kept, Roman Urdu
voice notes."""

import asyncio
import io
import zipfile
from types import SimpleNamespace as N


def test_a_person_takes_over_only_when_the_customer_asks():
    from app.modules.pi.service_conversation import ServiceTurn, needs_person

    turn = ServiceTurn(reply="x", request_human=True)

    def asks(text: str) -> bool:
        return needs_person(turn, {"latest_customer_message": text})

    assert asks("I want to talk to a human")
    assert asks("insaan se baat karni hai")
    assert not asks("I already paid for the AI system, match my payment")
    assert not asks("AI interviews are replacing human recruiters " * 20)  # a transcript
    assert not asks("human resources app chahiye")


def test_pi_never_repeats_itself_or_asks_to_send_twice():
    from app.modules.pi.service_conversation import repeats_itself, wordy_status

    said = "The team will send the meeting link here shortly once it is ready."
    ctx = {"history": [{"role": "ai", "text": said}], "latest_customer_message": "link?"}
    assert repeats_itself(f"Sure. {said}", ctx)
    asked = {
        "history": [{"role": "ai", "text": "• Website\nShall I send this to the team?"}],
        "latest_customer_message": "tell me your services",
    }
    assert repeats_itself("We do branding.\nShall I send this to the team?", asked)
    assert wordy_status("• Web\n  • Status: paid\n  • Next Step: deliver")
    assert wordy_status("• Website: paid, the work is in progress") is None


def test_invoice_facts_the_customer_received_may_be_repeated():
    from app.modules.pi.service_conversation import allowed_text

    ctx = {
        "account": {
            "invoices": [
                {
                    "number": "INV-000003",
                    "status": "paid",
                    "total": "USD 2,500.00",
                    "paid": "USD 2,500.00",
                    "balance": "USD 0.00",
                }
            ],
            "balance": "nothing owed",
        }
    }
    allowed = allowed_text(ctx)
    assert "INV-000003" in allowed and "USD 2,500.00" in allowed


def test_gemini_media_uses_the_pinned_model_not_a_retired_default():
    from app.ai.registry import ModelRegistry

    pinned = ModelRegistry({"gemini": {"balanced": "gemini-3.5-flash"}})
    assert pinned.resolve("gemini", "video") == "gemini-3.5-flash"
    assert pinned.resolve("gemini", "vision") == "gemini-3.5-flash"
    assert ModelRegistry({"openai": {"balanced": "x"}}).resolve("openai", "transcribe") == (
        "whisper-1"
    )


def test_videos_and_office_files_are_kept():
    from app.modules.customers.files import PPTX, XLSX, sniff

    assert sniff(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 20) == "video/mp4"
    for part, kind in (("xl/workbook.xml", XLSX), ("ppt/presentation.xml", PPTX)):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(part, "<x/>")
        assert sniff(buffer.getvalue()) == kind


def test_an_urdu_voice_note_reads_in_roman_urdu():
    from app.modules.pi.runtime import roman_transcript

    class Manager:
        async def complete(self, scope, **kwargs):
            return N(text="Assalam o alaikum. Mujhe ek ERP system ki zaroorat hai")

    hindi = "अस्सलाम वालेकुम। मुझे एक ERP system की ज़रूरत है"
    assert asyncio.run(roman_transcript(Manager(), None, hindi, None)).startswith("Assalam")
    assert asyncio.run(roman_transcript(Manager(), None, "I need a website", None)) == (
        "I need a website"
    )


def test_status_only_when_asked_and_no_empty_promises():
    from app.modules.pi.service_conversation import (
        PERSON_WORDS,
        ServiceTurn,
        empty_promise,
        unasked_status,
    )

    listed = "Here's the current status of your projects:\n• Website: paid"
    assert unasked_status(listed, {"latest_customer_message": "Reply in Roman Urdu now"})
    assert unasked_status(listed, {"latest_customer_message": "any update?"}) is None
    wait = "I'll check the payment details and get back to you shortly."
    assert empty_promise(ServiceTurn(reply=wait), {})
    assert empty_promise(ServiceTurn(reply=wait, request_human=True), {}) is None
    assert PERSON_WORDS.search("Please transfer my situation to a real team member")
