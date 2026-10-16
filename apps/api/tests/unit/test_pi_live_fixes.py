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


def test_one_project_one_deal_and_no_confirmation_without_a_yes():
    from app.modules.pi.service_conversation import (
        DOCUMENT_TITLE,
        Project,
        ServiceTurn,
        confirmed_now,
        same_project,
        unconfirmed_brief,
    )

    assert same_project("SaaS Product Platform", "SaaS Product Platform Development")
    assert not same_project("SaaS Product Platform", "Video Editing SaaS Product")
    assert DOCUMENT_TITLE.search("Proposal QUO-000016")
    turn = ServiceTurn(
        reply="x", projects=[Project(title="SaaS Product Platform", status="confirmed")]
    )
    # An older brief was already sent, but this project is confirmed only now.
    brief = {"ready_for_team": True, "projects": [{"title": "Logo", "status": "confirmed"}]}
    assert confirmed_now(turn, brief) == ["SaaS Product Platform"]
    asked = {"brief": brief, "latest_customer_message": "Which saas product platform?"}
    assert unconfirmed_brief(turn, asked)
    assert unconfirmed_brief(turn, {**asked, "latest_customer_message": "yes send it"}) is None


def test_send_again_needs_the_documents_link() -> None:
    from app.modules.pi.service_conversation import link_not_resent

    link = "https://pi.example/d/8uBNH5aw7Epv3L6ly4es"
    context = {
        "latest_customer_message": "Missing please send me again",
        "project_deals": [{"project": "SaaS", "links": f"proposal QUO-000019: {link}"}],
    }
    assert link_not_resent("Your proposals are shared and waiting.", context)
    assert link_not_resent(f"Here it is:\n• Proposal QUO-000019: {link}", context) is None
    context["latest_customer_message"] = "What's the status of my project?"
    assert link_not_resent("Proposal shared, waiting for your response.", context) is None


def test_a_resent_link_survives_the_number_filter() -> None:
    from app.modules.pi.service_conversation import allowed_text, without_blocked_lines

    link = "https://pi.example/d/Tal8SCbNUxJrGVpnsmnnaGZfbrHf9"
    context = {"project_deals": [{"project": "Video", "links": f"proposal QUO-000017: {link}"}]}
    reply = f"Here is your proposal again:\n• Proposal QUO-000017: {link}"
    assert without_blocked_lines(reply, "quote", allowed_text(context)) == reply


def test_mixed_english_and_roman_urdu_is_english() -> None:
    from app.modules.pi.language import TEAM_CHECK_NOTICES, detect_language

    assert detect_language("Bas yehi, that's all") == "en"
    assert detect_language("website design chahiye") == "roman_ur"
    assert "batata hoon" not in TEAM_CHECK_NOTICES["roman_ur"]


def test_no_send_offer_before_any_detail() -> None:
    from app.modules.pi.service_conversation import (
        STATUS_HEADER,
        Project,
        ServiceTurn,
        asks_too_early,
    )

    turn = ServiceTurn(
        reply="Noted. You want:\n• A website for your car showroom\nShall I send this to the team?",
        projects=[Project(title="Website for Car Showroom")],
    )
    context = {"latest_customer_message": "I need a website for my car showroom"}
    assert asks_too_early(turn, context)
    turn.projects[0].features = ["cars with prices", "test drive booking"]
    assert asks_too_early(turn, context) is None
    turn.projects[0].features = []
    assert asks_too_early(turn, {"latest_customer_message": "bas yehi, that's all"}) is None
    reply = "Here's the current status of your projects:\n\n• Website: collecting details"
    assert STATUS_HEADER.sub("", reply, count=1) == "• Website: collecting details"


def test_that_s_all_never_gets_anything_else() -> None:
    from app.modules.pi.service_conversation import ServiceTurn, without_open_question

    turn = ServiceTurn(
        reply="Got it. You want:\n• A website\n• A mobile app\n\n"
        "Is there anything else you want to add?",
        language="en",
    )
    reply = without_open_question(turn, {"latest_customer_message": "Bas yehi, that's all"})
    assert "anything else" not in reply
    assert reply.endswith("Shall I send this to the team so they can prepare your proposal?")
    assert "• A mobile app" in reply and turn.awaiting_customer


def test_a_status_question_gets_every_projects_status() -> None:
    from app.modules.pi.service_conversation import status_lines, status_missed

    context = {
        "latest_customer_message": "What's the status of my projects?",
        "project_deals": [
            {"project": "Website for Car Showroom", "status": "brief sent", "next": "proposal"},
            {"project": "Mobile App for Booking Test Drives", "status": "brief sent", "next": "x"},
        ],
    }
    summary = "You want:\n• A mobile app\n\nIs there anything else you want to add?"
    assert status_missed(summary, context)
    built = status_lines(context)
    assert built.count("• ") == 2 and status_missed(built, context) is None
    context["latest_customer_message"] = "Customers should see cars with prices"
    assert status_missed(summary, context) is None


def test_a_rewrite_drops_what_pi_already_sent() -> None:
    from app.modules.pi.service_conversation import without_repeats

    summary = (
        "Noted. You want:\n• A mobile app for booking test drives\n• A website for your "
        "car showroom\n\nIs there anything else you want to add, or is this everything?"
    )
    context = {"history": [{"role": "ai", "text": summary}]}
    reply = summary + "\n\nYour proposal QUO-000009 is shared here."
    assert without_repeats(reply, context) == "Your proposal QUO-000009 is shared here."
    assert without_repeats(summary, context) == summary  # nothing new: left as it was


def test_a_booking_feature_is_not_a_meeting_claim() -> None:
    from app.modules.pi.service_conversation import invented

    context = {"history": [], "latest_customer_message": "This is what we need"}
    feature = "The app lets customers book a test drive appointment, confirmed on WhatsApp."
    assert invented(feature, context) == ""
    assert invented("Your meeting with our team is confirmed for Friday.", context)


def test_a_refused_reply_keeps_what_the_turn_understood() -> None:
    from uuid import uuid4

    from app.modules.pi.models import PiConversation
    from app.modules.pi.service_conversation import Project, ServiceTurn, keep_notes

    conversation = PiConversation(id=uuid4(), service_brief={"projects": []})
    turn = ServiceTurn(
        reply="(refused)",
        projects=[
            Project(title="Showroom ERP", features=["inventory", "installments"]),
            Project(title="Customer app", status="confirmed", features=["test drives"]),
        ],
    )
    keep_notes(conversation, turn)
    saved = {p["title"]: p for p in conversation.service_brief["projects"]}
    assert saved["Showroom ERP"]["features"] == ["inventory", "installments"]
    assert saved["Customer app"]["status"] == "collecting"  # never confirmed by a refusal


def test_an_unreadable_link_is_said_plainly() -> None:
    from app.modules.pi.service_conversation import ServiceTurn, link_unread

    context = {"shared_links": [{"url": "https://www.pakwheels.com", "unreadable": True}]}
    turn = ServiceTurn(reply="You want to check PakWheels. What do you want to discuss?")
    assert link_unread(turn, context)
    turn.reply = "I couldn't open that link here. What do you like about it?"
    assert not link_unread(turn, context)
    assert not link_unread(turn, {"shared_links": [{"url": "x", "unreadable": False}]})


def test_yes_to_send_sends_and_that_s_all_never_hands_over() -> None:
    from app.modules.pi.service_conversation import ServiceTurn, needs_person, send_now

    asked = (
        "Understood, you have confirmed:\n• A complete ERP system for your car showroom\n"
        "• A customer app for Android and iPhone\n\nShall I send this to the team so they "
        "can prepare your proposal?"
    )
    context = {
        "latest_customer_message": "yes",
        "history": [{"role": "ai", "text": asked}],
        "brief": {
            "projects": [
                {"title": "ERP System for Car Showroom", "status": "collecting"},
                {"title": "Customer App", "status": "collecting"},
                {"title": "AI Interview Taker Project", "status": "collecting"},
            ]
        },
    }
    turn = ServiceTurn(reply="Is there anything else you would like to add?", language="en")
    send_now(turn, context)
    assert turn.ready_for_team and not turn.awaiting_customer
    assert sorted(p.title for p in turn.projects if p.status == "confirmed") == [
        "Customer App",
        "ERP System for Car Showroom",
    ]
    assert "anything else" not in turn.reply
    closing = ServiceTurn(reply="ok", wants_person=True)
    assert not needs_person(closing, {"latest_customer_message": "Bas yehi, that's all"})
    assert needs_person(ServiceTurn(reply="ok"), {"latest_customer_message": "talk to a human"})


def test_a_ready_brief_confirms_the_projects_it_names() -> None:
    from app.modules.pi.service_conversation import Project, ServiceTurn, confirm_summarised

    turn = ServiceTurn(
        reply="I'll send the ERP and customer app requirements to the team now.",
        ready_for_team=True,
        projects=[
            Project(title="ERP System for Car Showroom"),
            Project(title="Customer App"),
            Project(title="AI Interview Taker Project"),
        ],
    )
    confirm_summarised(turn, {"history": []})
    status = {p.title: p.status for p in turn.projects}
    assert status["ERP System for Car Showroom"] == "confirmed"
    assert status["Customer App"] == "confirmed"
    assert status["AI Interview Taker Project"] == "collecting"


def test_yes_to_a_meeting_question_is_about_the_meeting() -> None:
    from app.modules.pi.service_conversation import ServiceTurn, meeting_yes

    context = {
        "latest_customer_message": "yes",
        "history": [
            {
                "role": "ai",
                "text": "You requested a meeting today at 5 PM. Shall I confirm "
                "this time with the team?",
            }
        ],
    }
    turn = ServiceTurn(
        reply="Your ERP system and customer app requirements will be sent to the team now.",
        language="en",
    )
    meeting_yes(turn, context)
    assert turn.meeting_requested
    assert turn.reply.startswith("Done. I've asked the team to confirm that time")
    other = ServiceTurn(reply="Great.", language="en")
    meeting_yes(
        other,
        {
            "latest_customer_message": "yes",
            "history": [{"role": "ai", "text": "Shall I send this to the team?"}],
        },
    )
    assert not other.meeting_requested


def test_an_arranged_meeting_survives_a_new_time_request() -> None:
    from app.modules.pi.service_conversation import ServiceTurn, arranged_meeting, merged_meeting

    booked = {
        "starts_at": "2026-10-17T16:00",
        "how": "google_meet",
        "label": "Saturday 17 October, 04:00 PM",
        "link": "https://meet.jit.si/pi-meeting-1",
    }
    turn = ServiceTurn(reply="ok", meeting_time="2026-10-16T17:00")
    after = merged_meeting(booked, turn)
    assert after["link"] == booked["link"] and after["starts_at"] == booked["starts_at"]
    assert after["change_to"] == "2026-10-16T17:00"
    assert arranged_meeting({"brief": {"meeting": after}})["label"] == booked["label"]
    assert merged_meeting(booked, ServiceTurn(reply="ok"))["link"] == booked["link"]
