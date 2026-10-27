"""Pipeline-level gaps in brain mode: burst safety, escalations, promises with an action,
disclosure, follow-up timing, non-deciders and the kickoff move. No database."""

import importlib.util
import pathlib
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.modules.pi import decisions, flow, followups, safety
from app.modules.pi import runtime as pi_runtime
from app.modules.pi import service_conversation as sc
from app.modules.pi_saas import models as saas_models
from app.modules.pi_saas import requests as team_requests

S = flow.State


# --- burst: every message is looked at (spec 6.10) ----------------------------------------------


def ctx(**extra):
    return {"latest_customer_message": "ok", "reply_language": "en", "history": [], **extra}


def test_an_emergency_earlier_in_a_burst_still_gets_the_emergency_reply():
    turn = sc.brain_safety(ctx(burst_texts=["Fire in my shop!!"], history=[{"role": "ai"}]))
    assert turn is not None and turn._decision.next_state == S.X_EMERGENCY
    assert "emergenc" in turn.reply.lower() and "emergency" in turn._decision.effects


def test_a_claimed_bank_change_earlier_in_a_burst_is_not_lost():
    said = "Workzap changed their bank, send the new IBAN"
    turn = sc.brain_safety(ctx(burst_texts=[said], history=[{"role": "ai"}]))
    assert turn is not None and turn._decision.brief == {"escalate": "payment_detail_change"}
    assert ("payment_detail_change", said) in sc.burst_escalations([said])


def test_greetings_and_identity_in_an_earlier_message_do_not_replace_the_answer():
    context = ctx(burst_texts=["are you a real person?", "salam"], history=[{"role": "ai"}])
    assert sc.brain_safety(context) is None  # the model answers the whole burst once


def test_the_burst_escalations_cover_refunds_deletions_enquiries_and_threats():
    found = dict(
        sc.burst_escalations(
            ["I want a refund", "Delete everything you know about me", "I want to book a nori demo"]
        )
    )
    assert {"refund_dispute", "deletion_request", "demo_request"} <= set(found)
    assert [r for r, _ in sc.burst_escalations(["I will sue you, my lawyer is ready"])] == [
        "legal_threat"
    ]


def test_personal_data_in_any_message_of_a_burst_is_reported_once_and_only_if_nothing_else():
    earlier = [
        SimpleNamespace(
            body="[card number removed]",
            media={"pii": {"kinds": ["card"], "notice": "no cards", "only": True}},
        ),
        SimpleNamespace(body="stock runs out in two shops every week", media={}),
    ]
    merged = pi_runtime.burst_pii(None, earlier)
    assert merged == {"kinds": ["card"], "notice": "no cards", "only": False}
    latest = {"kinds": ["id"], "notice": "no ids", "only": True}
    both_empty = pi_runtime.burst_pii(latest, earlier[:1])
    assert both_empty == {"kinds": ["card", "id"], "notice": "no cards no ids", "only": True}
    assert pi_runtime.burst_pii(None, []) is None


# --- promises with an action (M3, M6, E7, E8) ---------------------------------------------------


def test_m6_another_payment_way_raises_a_change_request():
    effects, marks = sc.BOUNDARY_EFFECTS[safety.Boundary.OTHER_PAY]
    assert effects == ["escalate"] and marks == {"escalate": "payment_method"}
    turn = sc.brain_safety(ctx(latest_customer_message="Can I pay by JazzCash?"))
    assert turn is not None and turn._decision.brief == {"escalate": "payment_method"}


def test_m3_bank_details_after_approval_resend_the_approved_quote():
    turn = sc.brain_safety(
        ctx(
            latest_customer_message="send me your bank details",
            flow={"state": "S10_AWAITING_PAYMENT"},
            history=[{"role": "ai"}],
        )
    )
    assert turn is not None and "resend_quote" in turn._decision.effects
    assert "resend" in turn.reply
    before = sc.brain_safety(
        ctx(latest_customer_message="send me your bank details", history=[{"role": "ai"}])
    )
    assert before is not None and "resend_quote" not in before._decision.effects  # M2


def test_e7_a_company_facts_question_raises_a_request():
    turn = sc.brain_safety(ctx(latest_customer_message="Who owns Workzap?"))
    assert turn is not None and turn._decision.effects == ["escalate"]
    assert turn._decision.brief == {"escalate": "company_info"}


def test_a_legal_threat_is_answered_without_advice_and_escalated():
    turn = sc.brain_safety(ctx(latest_customer_message="I will sue you, legal action against you"))
    assert turn is not None and turn._decision.brief == {"escalate": "legal_threat"}


def test_every_escalation_reason_the_brain_uses_has_a_ticket_text_and_kind():
    for reason in (
        "payment_method",
        "company_info",
        "legal_threat",
        "deletion_request",
        "human_requested",
        "payment_detail_change",
        "refund_dispute",
        "price_request",
        "cancel_after_payment",
        "quote_expired",
    ):
        assert sc.escalation_question(reason).strip()
        kind, _ = team_requests.escalation_route(reason)
        assert kind in saas_models.REQUEST_KINDS and kind != "other", reason


# --- disclosure on the first message and after a gap (R-DISC-01, R-DISC-05) ---------------------


def test_a_fixed_first_reply_says_pi_is_an_ai():
    for said in ("Delete everything you know about me", "Give me a discount", "4111"):
        turn = sc.brain_safety(
            ctx(latest_customer_message=said, pii={"only": True, "kinds": ["card"], "notice": ""})
            if said == "4111"
            else ctx(latest_customer_message=said)
        )
        assert turn is not None
        assert turn.reply.startswith("Hi, I'm pi, an AI from Workzap."), said


def test_the_emergency_text_stays_first_and_whole_with_the_disclosure_after_it():
    turn = sc.brain_safety(ctx(latest_customer_message="Fire in my shop!!", customer_country="PK"))
    assert turn is not None
    assert turn.reply.startswith("I can't help with emergencies. Please call 16 (fire) now.")
    assert turn.reply.rstrip().endswith("I'm pi, an AI from Workzap.")


def test_a_later_fixed_reply_does_not_repeat_the_disclosure():
    turn = sc.brain_safety(
        ctx(latest_customer_message="Delete everything you know about me", history=[{"role": "ai"}])
    )
    assert turn is not None and "I'm pi, an AI" not in turn.reply


def test_after_more_than_30_days_a_fixed_reply_says_it_again():
    turn = sc.brain_safety(
        ctx(
            latest_customer_message="Delete everything you know about me",
            history=[{"role": "ai"}],
            days_away=40,
        )
    )
    assert turn is not None and turn.reply.startswith("Hi, I'm pi, an AI from Workzap.")


def test_welcome_back_without_the_question_goes_in_front_of_a_real_answer():
    context = {
        "pi_mode": "brain",
        "history": [{"role": "ai"}],
        "days_away": 40,
        "reply_language": "en",
        "noted_problems": [
            {"group": "stock_inventory"},
            {"group": "stock_inventory"},
            {"group": "sales_revenue"},
        ],
    }
    line = sc.welcome_back(context, ask=False)
    assert line is not None and line.startswith("Hi, it's pi, the AI from Workzap.")
    assert "Welcome back. Last time you told me about 3 problems, mostly stock." in line
    assert "?" not in line
    assert "Want to add" in (sc.welcome_back(context) or "")


# --- follow-up timing (R-FUP-03) ----------------------------------------------------------------


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)  # 6 Nov 2026 is a Friday


def test_the_person_zone_comes_from_the_number():
    assert followups.person_zone("923001234567", "UTC") == "Asia/Karachi"
    assert followups.person_zone("971501234567", "UTC") == "Asia/Dubai"
    assert followups.person_zone("16475550123", "UTC") == "America/Toronto"
    assert followups.person_zone("16045550123", "UTC") == "America/Vancouver"
    assert followups.person_zone("447700900123", "Asia/Karachi") == "Asia/Karachi"
    assert followups.person_zone(None, "UTC") == "UTC"


def test_friday_prayers_are_12_00_to_14_30_and_only_for_pakistan_and_uae_numbers():
    karachi = "Asia/Karachi"
    assert not followups._friday_prayer(karachi, at(6, 6, 59))  # 11:59
    assert followups._friday_prayer(karachi, at(6, 7, 0))  # 12:00
    assert followups._friday_prayer(karachi, at(6, 9, 29))  # 14:29
    assert not followups._friday_prayer(karachi, at(6, 9, 30))  # 14:30
    assert not followups._friday_prayer(karachi, at(5, 7, 30))  # Thursday
    policy = SimpleNamespace(timezone="Asia/Karachi", whatsapp_config={})
    friday_noon = at(6, 7, 15)  # 12:15 Friday in Karachi
    assert followups.blocked_until(policy, "923001234567", friday_noon) is not None
    assert followups.blocked_until(policy, "971501234567", at(6, 8, 15)) is not None  # 12:15 UAE
    # a Canadian number is not under Jumu'ah (and 12:15 Karachi is 02:15 in Toronto: but quiet
    # hours there are over only after 09:00, so look at a Toronto afternoon)
    toronto_afternoon = at(6, 17, 30)  # 12:30 Friday in Toronto
    assert followups.blocked_until(policy, "16475550123", toronto_afternoon) is None


def test_quiet_hours_use_the_zone_of_the_persons_number_not_the_workspace_zone():
    policy = SimpleNamespace(timezone="UTC", whatsapp_config={})
    # 04:00 UTC is 09:00 in Karachi (awake) but 04:00 for a workspace in UTC (quiet)
    assert followups.blocked_until(policy, "923001234567", at(4, 4, 0)) is None
    assert followups.blocked_until(policy, "447700900123", at(4, 4, 0)) is not None
    # 16:30 UTC is 21:30 in Karachi: quiet there, fine on the workspace clock
    assert followups.blocked_until(policy, "923001234567", at(4, 16, 30)) is not None
    assert followups.blocked_until(policy, "447700900123", at(4, 16, 30)) is None


def test_iftar_timing_still_reads_the_existing_config():
    policy = SimpleNamespace(
        timezone="UTC",
        whatsapp_config={
            "ramadan": [{"start": "2026-11-01", "end": "2026-11-30"}],
            "maghrib": "17:30",
            "quiet_start": 0,
            "quiet_end": 0,
        },
    )
    # 17:00 in Karachi is 12:00 UTC: inside the hour before Maghrib
    assert followups.blocked_until(policy, "923001234567", at(4, 12, 0)) is not None
    assert followups.blocked_until(policy, "923001234567", at(4, 9, 0)) is None


# --- the offer to someone who is not the decision-maker (R-OFFER-06) ---------------------------


@pytest.mark.parametrize(
    "said",
    [
        "I'm the store manager at a pharmacy chain. My boss asked me to tell you our problems.",
        "I work at Al Noor Traders",
        "my boss decides these things",
        "I'm not the owner",
        "I am not the decision maker here",
        "mere boss decide karte hain",
        "It's not my decision",
    ],
)
def test_a_person_who_is_not_the_decider_is_detected(said):
    assert decisions.non_decider(said)


@pytest.mark.parametrize(
    "said",
    [
        "I own three pharmacies",
        "I work at my own shop all day",
        "Stock runs out every week",
        "my manager is great but the till is slow",
        "",
    ],
)
def test_owners_and_ordinary_talk_are_not_demoted(said):
    assert not decisions.non_decider(said)


def test_send_the_quote_from_a_non_decider_gets_the_members_answer_and_one_question():
    facts = {"can_approve": False, "business": "Bright Pharmacy", "problem_count": 3}
    first = decisions.decide(S.S4_SORTED_SUMMARY, "send the quote", "en", facts)
    assert first is not None and first.next_state is None and first.effects == []
    assert "The owner of Bright Pharmacy needs to say yes" in first.reply
    assert "workzap.ai/pi/talk-to-pi" in first.reply
    assert first.reply.count("?") == 1 and first.reply.rstrip().endswith("?")
    assert "number" not in first.reply.lower()  # never asks for the decision-maker's number
    again = decisions.decide(
        S.S5_READINESS, "yes", "en", {**facts, "brief": {"non_decider_asked": True}}
    )
    assert again is not None and "?" not in again.reply  # asked once only


def test_a_decider_asking_for_the_quote_is_not_blocked():
    # Platform spec Book 4 5.2 (G28): asking for the document or quote is itself the yes
    facts = {"can_approve": True, "problem_count": 3, "problem_refs": ["a", "b", "c"]}
    said = decisions.decide(S.S4_SORTED_SUMMARY, "send the quote", "en", facts)
    assert said is not None and said.next_state == S.S6_PREPARING and "?" not in said.reply


# --- consent for follow-ups beyond 24 hours (spec 3.9.1) ----------------------------------------


def test_the_consent_question_text_matches_the_one_the_buttons_and_brief_look_for():
    assert decisions.CONSENT_ASK["en"] == sc.CONSENT_QUESTION["en"]
    assert decisions.CONSENT_ASK["roman_ur"] == sc.CONSENT_QUESTION["roman_ur"]


def test_consent_is_asked_with_the_offers_yes_and_with_later_only_when_unknown():
    facts = {"ask_consent": True, "problem_count": 2, "group_count": 1, "problem_refs": ["a", "b"]}
    yes = decisions.decide(S.S5_READINESS, "yes", "en", facts)
    assert yes is not None and yes.reply.endswith(sc.CONSENT_QUESTION["en"])
    later = decisions.decide(S.S5_READINESS, "later", "en", facts)
    assert later is not None and later.next_state == S.X_PAUSED
    assert later.reply.endswith(sc.CONSENT_QUESTION["en"])
    known = decisions.decide(S.S5_READINESS, "yes", "en", {**facts, "ask_consent": False})
    assert known is not None and "Can I message you" not in known.reply
    urdu = decisions.decide(S.S5_READINESS, "haan", "roman_ur", facts)
    assert urdu is not None and urdu.reply.endswith(sc.CONSENT_QUESTION["roman_ur"])


# --- S12 to S13 (spec 3.2) ----------------------------------------------------------------------


def chat(state, **brief):
    return SimpleNamespace(flow_state=state.value, service_brief=brief, flow_state_since=None)


def test_the_kickoff_done_moves_the_chat_into_the_build():
    conversation = chat(S.S12_KICKOFF, kickoff={"at": "2026-11-10T10:00:00+00:00"})
    assert not flow.kickoff_done(conversation, datetime(2026, 11, 10, 10, 30, tzinfo=UTC))
    assert flow.kickoff_done(conversation, datetime(2026, 11, 10, 11, 0, tzinfo=UTC))
    assert conversation.flow_state == "S13_IN_BUILD"
    assert conversation.service_brief["kickoff"]["done_at"].startswith("2026-11-10T11:00")
    assert not flow.kickoff_done(conversation, datetime(2026, 11, 11, tzinfo=UTC))  # once


def test_a_kickoff_without_a_known_time_or_another_state_stays_put():
    assert not flow.kickoff_done(chat(S.S12_KICKOFF, kickoff={}), datetime.now(UTC))
    assert not flow.kickoff_done(chat(S.S11_PAYMENT_CONFIRMED), datetime.now(UTC))


# --- the ticket (spec 6.6) ---------------------------------------------------------------------


def test_each_reason_has_its_own_kind_and_emergencies_and_bank_claims_are_urgent():
    assert team_requests.escalation_route("emergency") == ("emergency", "urgent")
    assert team_requests.escalation_route("payment_detail_change") == (
        "payment_detail_change",
        "urgent",
    )
    assert team_requests.escalation_route("refund_dispute") == ("refund", "high")
    assert team_requests.escalation_route("demo_request") == ("demo_request", "high")
    assert team_requests.escalation_route("enterprise_lead")[0] == "enterprise_lead"
    assert team_requests.escalation_route("abuse_threat") == ("abuse", "high")
    assert team_requests.escalation_route("legal_threat") == ("legal_threat", "high")
    assert team_requests.escalation_route("complaint", "pi keeps getting it wrong")[0] == (
        "complaint_about_pi"
    )
    assert team_requests.escalation_route("complaint", "Workzap was late")[0] == (
        "complaint_about_workzap"
    )
    assert team_requests.escalation_route("nonsense") == ("other", "high")


def test_every_escalation_kind_and_the_urgent_priority_are_allowed_by_the_database():
    assert set(saas_models.ESCALATION_KINDS) <= set(saas_models.REQUEST_KINDS)
    assert "urgent" in saas_models.REQUEST_PRIORITIES
    path = pathlib.Path(__file__).parents[2] / "migrations/versions/0045_pi_request_reasons.py"
    spec = importlib.util.spec_from_file_location("m0045", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.NEW_KINDS) == set(saas_models.ESCALATION_KINDS)
    assert set(module.OLD_KINDS) | set(module.NEW_KINDS) == set(saas_models.REQUEST_KINDS)
    assert all(len(k) <= 24 for k in saas_models.REQUEST_KINDS)  # the column is String(24)


def test_the_honest_unclaimed_line_promises_no_time():
    assert team_requests.UNCLAIMED_TEXT["en"] == (
        "The Workzap team hasn't picked this up yet. I've flagged it again."
    )
    assert not any(c.isdigit() for c in team_requests.UNCLAIMED_TEXT["en"])
    assert team_requests.sla_minutes(None) == 30  # spec v1.4, 17.7
    assert team_requests.sla_minutes({"brain": {"handover_sla_minutes": 1}}) == 5
    assert team_requests.sla_minutes({"brain": {"handover_sla_minutes": 30}}) == 30
    assert team_requests.sla_minutes({"brain": {"handover_sla_minutes": 10**6}}) == 1440


# --- small fixes --------------------------------------------------------------------------------


def test_the_brain_file_notice_has_no_exclamation_mark_and_the_question_comes_last():
    for text in pi_runtime.BRAIN_MEDIA_UNREADABLE_NOTICES.values():
        assert "!" not in text
        assert text.count("?") + text.count("؟") == 1
        assert text.rstrip().endswith(("?", "؟"))


def test_every_alert_kind_fits_the_notification_column():
    for kind in saas_models.REQUEST_KINDS:
        assert len(team_requests.notification_kind(kind)) <= 32, kind
    assert len("pi.request.unclaimed") <= 32


def test_a_reply_that_says_noted_without_recording_a_problem_is_sent_back() -> None:
    """Production chat 2026-10-24: 'I've noted it: ...' with zero problems stored."""
    from types import SimpleNamespace

    from app.modules.pi.problems import ProblemNote, ProblemOp
    from app.modules.pi.service_conversation import noted_without_problem

    said = "Thanks. I've noted it: software that edits videos. Anything else getting in the way?"
    empty = SimpleNamespace(reply=said, problem_ops=[])
    assert "problem_ops is empty" in noted_without_problem(empty)
    op = ProblemOp(op="create", note=ProblemNote(title="Credits cost too much", user_words=["x"]))
    assert noted_without_problem(SimpleNamespace(reply=said, problem_ops=[op])) == ""
    plain = SimpleNamespace(reply="Samajh gaya. Kya aap thora aur bata sakte hain?", problem_ops=[])
    assert noted_without_problem(plain) == ""


def test_the_noted_claim_covers_the_other_ways_pi_says_it_noted_something() -> None:
    """Real sweep 2026-10-25: 'Thanks, that's noted.' and 'I've got that' with nothing recorded."""
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import noted_without_problem

    for said in (
        "Thanks, that's noted. Is there anything else you want to add?",
        "I've added that animals aren't weighed regularly. Anything else?",
        "Thanks, I've got that. What else is slowing you down?",
        "Shukriya, noted. Kya aap kuch aur batana chahenge?",
    ):
        assert noted_without_problem(SimpleNamespace(reply=said, problem_ops=[])), said
    assert (
        noted_without_problem(
            SimpleNamespace(reply="Samajh gaya. Kya hota hai phir?", problem_ops=[])
        )
        == ""
    )


def test_a_whole_sentence_is_never_bold_but_the_summary_group_names_are() -> None:
    """Real sweep: pi bolded the owner's sentence back at them in WhatsApp."""
    from app.modules.pi.service_conversation import polished

    quoted = "Noted: *cars come back with scratches the customer says were there*. What next?"
    assert "*" not in polished(quoted)
    assert "*har hafte stock ka mismatch hota hai*" not in polished(
        "Samajh gaya: *har hafte stock ka mismatch hota hai*. Phir?"
    )
    summary = "*Marketing and leads* (2)\n• Late replies\n\n*Operations and workflow* (1)\n• Slow"
    assert polished(summary) == summary
    assert polished("The *bold word* stays") == "The *bold word* stays"


def test_pi_does_not_say_you_are_right_when_the_owner_corrected_nothing() -> None:
    """Real sweep: 'You're right. I've changed it to ...' after a plain extra detail."""
    from app.modules.pi import constitution

    def hits(said: str, reply: str, **context) -> list[str]:
        ctx = {"latest_customer_message": said, "flow": {"state": "S3_NOTED"}, **context}
        return [v.rule for v in constitution.lint(reply, ctx) if v.rule == "R-CORR-04"]

    reply = "You're right. I've changed it to: design changes every week. What next?"
    assert hits("It happens every week and I am not sure how much we lose.", reply)
    assert hits("Haan har hafte hota hai", "Aap sahi keh rahe hain, badal diya. Phir?")
    assert not hits("Actually it is every day, not weekly", reply)
    assert not hits("that's not what I said", reply, said_wrong=True)
    assert not hits("Haan har hafte hota hai", "Samajh gaya. Phir kya hota hai?")


def test_the_unclaimed_line_follows_the_language_of_the_last_message():
    # live chat A (spec v1.4, 17.7): an English line in a Roman Urdu chat
    roman = team_requests.unclaimed_text("en", "Maslay bohat hain, koi nahi uthata")
    assert roman == team_requests.UNCLAIMED_TEXT["roman_ur"]
    assert (
        team_requests.unclaimed_text("roman_ur", "please call me")
        == (team_requests.UNCLAIMED_TEXT["en"])
    )
    assert (
        team_requests.unclaimed_text("roman_ur", "ok") == team_requests.UNCLAIMED_TEXT["roman_ur"]
    )
    assert team_requests.unclaimed_text(None, None) == team_requests.UNCLAIMED_TEXT["en"]
    assert (
        team_requests.unclaimed_text("en", "مرحبا كيف الحال") == team_requests.UNCLAIMED_TEXT["ar"]
    )
