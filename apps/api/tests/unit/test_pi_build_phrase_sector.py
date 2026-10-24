# ruff: noqa: E501
"""The Workzap line is not worded for shops when the industry is not one (real-model finding: a
dental clinic was told "past customers hear from you when new stock lands")."""

from app.modules.pi import solution_ask, solutions
from app.modules.pi.solution_context import _sector


def test_a_clinic_does_not_hear_about_new_stock() -> None:
    sector = _sector("dental_clinics")
    assert sector and sector.startswith("7.I")
    phrase = solutions.build_phrase("customer_messaging", "en", sector)
    assert "stock" not in phrase.lower()
    assert "next visit" in phrase


def test_a_factory_does_not_get_every_branch() -> None:
    phrase = solutions.build_phrase("dashboards_reports", "en", "7.D Manufacturing and industry")
    assert "branch" not in phrase.lower()
    roman = solutions.build_phrase(
        "dashboards_reports", "roman_ur", "7.D Manufacturing and industry"
    )
    assert "branch" not in roman.lower()


def test_shop_sectors_and_unknown_keep_the_spec_wording() -> None:
    spec = solutions.CATALOGUE["customer_messaging"]["en"]
    assert (
        solutions.build_phrase("customer_messaging", "en", "7.A Retail and consumer (part 1)")
        == spec
    )
    assert solutions.build_phrase("customer_messaging", "en", None) == spec
    assert solutions.build_phrase("customer_messaging", "en") == spec


def test_builds_with_no_shop_words_are_unchanged_everywhere() -> None:
    for key in ("booking_scheduling", "credit_ledger", "job_tracking"):
        assert (
            solutions.build_phrase(key, "en", "7.I Health and care")
            == solutions.CATALOGUE[key]["en"]
        )


def test_neutral_phrases_pass_the_tool_word_rule() -> None:
    for entry in solutions.NEUTRAL_PHRASES.values():
        for text in entry.values():
            assert solutions.banned_tool_words(text) == []


def test_bridge_uses_the_sector() -> None:
    problem = {"id": "p1", "workzap_build": {"keys": ["customer_messaging"]}}
    line = solution_ask.bridge({}, problem, "en", "7.I Health and care")
    assert line and "stock" not in line["says"].lower()


def test_their_own_distinctive_word_beats_a_wrong_subtype() -> None:
    """Real-model finding: "udhaar ka hisaab gadbad" was noted as cash_mismatch and got the cash
    count ideas instead of the credit ones."""
    from app.modules.pi import solution_ideas

    problems = solutions.load("kiryana_corner_shops_and_convenience_stores")["problems"]
    hit = solution_ideas.match_problem(
        problems, "cash_collections", "cash_mismatch", "Udhaar hisaab gadbad udhaar hisaab kitaab"
    )
    assert hit and hit["id"] == "p1_credit_customers"
    # With no such word the sub-type still decides.
    hit = solution_ideas.match_problem(problems, "cash_collections", "cash_mismatch", "galla match")
    assert hit and hit["id"] == "p3_cash_mismatch"


def test_a_shared_word_with_the_subtypes_entry_keeps_the_subtype() -> None:
    """Real-model finding: orders mixed across phone, WhatsApp and food apps went to the
    reservations entry because "phone" is only in that one."""
    from app.modules.pi import solution_ideas

    problems = solutions.load("restaurants")["problems"]
    hit = solution_ideas.match_problem(
        problems,
        "tech_systems",
        "software_not_connected",
        "Orders mixed across channels orders from phone WhatsApp and food apps",
    )
    assert hit and hit["id"] == "p5_software_not_connected"


def test_no_idea_at_the_offer_ends_on_the_offer_question_not_a_dead_end() -> None:
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import brain_no_ideas

    def turn() -> SimpleNamespace:
        return SimpleNamespace(
            reply="Ji.",
            _summary=False,
            _decision=None,
            request_human=False,
            _free=False,
            awaiting_customer=False,
        )

    context = {
        "reply_language": "en",
        "history": [{"role": "ai", "text": "Hi, I'm pi."}],
        "latest_customer_message": "any solution?",
        "solution_asked_no_ideas": True,
        "flow": {"state": "S5_READINESS"},
    }
    at_offer = turn()
    brain_no_ideas(at_offer, context)
    assert at_offer.reply.rstrip().endswith("You can say no.")
    declined = turn()
    brain_no_ideas(declined, {**context, "flow": {"state": "S5b_DECLINED"}})
    assert "solution document and a quote" not in declined.reply.split("\n\n")[-1]


def test_a_subtype_this_industry_has_no_entry_for_does_not_trigger_the_word_bonus() -> None:
    from app.modules.pi import solution_ideas

    problems = solutions.load("restaurants")["problems"]
    hit = solution_ideas.match_problem(
        problems,
        "communication_coordination",
        "info_lost_in_whatsapp",
        "orders from phone WhatsApp and food apps",
    )
    assert hit is None or hit["id"] != "p8_booking_appointments"


def test_a_reply_never_stops_on_the_bridge_opener() -> None:
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import strip_dangling_opener

    opener = solutions.BRIDGE_OPENERS[0]["en"]
    turn = SimpleNamespace(reply=f"Okay.\n• One.\n• Two.\n{opener}")
    strip_dangling_opener(turn)
    assert turn.reply == "Okay.\n• One.\n• Two."
    whole = SimpleNamespace(reply=f"Okay.\n{opener} reminders go out on time.")
    strip_dangling_opener(whole)
    assert whole.reply == f"Okay.\n{opener} reminders go out on time."
