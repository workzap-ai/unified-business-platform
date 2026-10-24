"""Three failures found by running a real-model conversation (gpt-4o-mini, 2026-10-24)."""

import pytest

from app.modules.pi import decisions, reply_voice, solution_ideas, solutions
from app.modules.pi import industry_packs as ip


@pytest.mark.parametrize(
    "said",
    [
        "haan document aur quote bana dein",
        "Yes please prepare the document and quote",
        "ji haan, solution document bhej dein",
    ],
)
def test_a_yes_that_asks_for_the_offered_document_is_an_explicit_yes(said):
    answer, sure = decisions.classify(said)
    assert answer == decisions.Answer.YES and sure >= decisions.YES_AT


@pytest.mark.parametrize(
    "said",
    [
        "ok",
        "hmm let me think about the document",
        "haan lekin pehle quote ka price batao",
        "maybe send the document later",
        "document kitne ka hoga?",
        "nahi, document nahi chahiye",
    ],
)
def test_hedged_or_negative_answers_about_the_document_are_still_not_a_yes(said):
    answer, sure = decisions.classify(said)
    assert not (answer == decisions.Answer.YES and sure >= decisions.YES_AT)


def test_the_noted_frame_is_translated_for_roman_urdu_and_arabic_only():
    en = "Thanks. I've noted it: udhaar ka total nahi pata. Aur kuch?"
    assert reply_voice.localise_noted(en, "roman_ur").startswith("Shukriya. Maine note kar liya:")
    assert reply_voice.localise_noted(en, "ar").startswith("شكرًا. سجلت ذلك:")
    assert reply_voice.localise_noted(en, "en") == en  # the first time keeps the canonical frame
    assert reply_voice.localise_noted(en, None) == en
    plain = "Samajh gaya. Kya aap thora aur bata sakte hain?"
    assert reply_voice.localise_noted(plain, "roman_ur") == plain


def test_a_problem_off_the_page_does_not_hide_an_earlier_problem_that_matches():
    found = ip.detect(["mera kiryana store hai, udhaar ka hisaab kitaab mein gadbad hai"])
    entries = solutions.load(found.primary)["problems"]
    credit = solution_ideas.match_problem(
        entries, "cash_collections", "", "Udhaar ka total nahi pata"
    )
    off_the_page = solution_ideas.match_problem(
        entries, "cash_collections", "", "Staff entry bhool jana"
    )
    assert credit is not None and off_the_page is None


def test_two_questions_are_repaired_in_place_without_a_model_call():
    from app.modules.pi import constitution

    context = {
        "pi_mode": "brain",
        "strict_voice": True,
        "flow": {"state": "S2_CLARIFYING"},
        "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap. Tell me more."}],
    }
    reply = "Samajh gaya. Kab se hai? Aur kitna nuksan hota hai?"
    broke = constitution.lint(reply, context)
    assert [v.rule for v in broke] == ["R-VOICE-02"]
    fixed = constitution.quiet_fix(reply, broke, context)
    assert fixed == "Samajh gaya. Aur kitna nuksan hota hai?"
    assert not constitution.lint(fixed, context)
    # another problem as well: the model is still needed
    hype = "Great question! Kab se hai? Aur kitna nuksan hota hai?"
    assert constitution.quiet_fix(hype, constitution.lint(hype, context), context) is None


def test_a_few_words_over_a_short_writers_length_does_not_send_the_draft_back():
    from app.modules.pi import constitution

    context = {
        "pi_mode": "brain",
        "strict_voice": True,
        "flow": {"state": "S2_CLARIFYING"},
        "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap. Tell me more."}],
        "style": {"reply_up_to_words": 25},
    }
    twenty_eight = " ".join(["lafz"] * 27) + " kya?"
    fifty = " ".join(["lafz"] * 49) + " kya?"
    assert not [v for v in constitution.lint(twenty_eight, context) if v.rule == "R-VOICE-01"]
    assert [v for v in constitution.lint(fifty, context) if v.rule == "R-VOICE-01"]


def test_the_noted_frame_is_rotated_so_the_same_opening_is_not_repeated():
    en = "Thanks. I've noted it: udhaar ka total nahi pata. Aur kuch?"
    for language in ("en", "roman_ur", "ar"):
        openings = [reply_voice.localise_noted(en, language, n).split(":")[0] for n in range(4)]
        assert len(set(openings)) == 4
    history = [
        {"role": "customer", "text": "mera masla"},
        {"role": "ai", "text": "Shukriya. Maine note kar liya: udhaar. Aur kuch?"},
        {"role": "ai", "text": "Theek hai, note kar liya: staff. Aur kuch?"},
        {"role": "ai", "text": "Kab se hai ye?"},
    ]
    assert reply_voice.noted_before({"history": history}) == 2


def test_a_problem_matches_by_sub_type_and_by_a_unique_category_entry():
    entries = solutions.load("salons_and_barbers")["problems"]
    by_subtype = solution_ideas.match_problem(
        entries, "customer_experience_digital", "booking_appointments", "Bookings are a mess"
    )
    assert by_subtype is not None and by_subtype["id"] == "p1_booking_appointments"
    # "customers_retention" has exactly one entry in this industry: a match without shared words
    retained = solution_ideas.match_problem(
        entries, "customers_retention", "", "Customers do not return"
    )
    assert retained is not None and retained["id"] == "p8_repeat_low"
    # two entries share loss_security: never guess between them
    assert (
        solution_ideas.match_problem(entries, "loss_security", "", "Something is missing") is None
    )


def test_the_extractor_runs_only_when_the_reply_model_wrote_no_problem():
    from app.modules.pi import problem_extract as pe

    base = {
        "pi_mode": "brain",
        "flow": {"state": "S2_CLARIFYING"},
        "latest_customer_message": "mera kiryana store hai aur udhaar ka hisaab gadbad hai",
    }
    assert pe.wants_extraction(base, "Samajh gaya.", [])
    assert not pe.wants_extraction(base, "Samajh gaya.", ["an op"])
    assert not pe.wants_extraction({**base, "flow": {"state": "S5_READINESS"}}, "x", [])
    assert not pe.wants_extraction({**base, "latest_customer_message": "haan theek"}, "x", [])
    assert not pe.wants_extraction(
        {**base, "solution_asked": True, "noted_problems": [{"ref": "p1"}]}, "x", []
    )
    assert not pe.wants_extraction({**base, "pi_mode": "standard"}, "x", [])


async def test_the_extractor_returns_checked_create_ops_and_never_raises():
    from types import SimpleNamespace

    from app.modules.pi import problem_extract as pe

    context = {"latest_customer_message": "udhaar ka hisaab gadbad hai", "noted_problems": []}

    class Good:
        async def complete_structured(self, scope, output, **kwargs):
            note = pe.SimpleNote(
                title="Credit totals not tracked",
                user_words=["udhaar ka hisaab gadbad hai"],
                category="cash_collections",
                subtype="credit_customers",
            )
            return SimpleNamespace(value=pe.Extracted(found=[note]))

    ops = await pe.extract(Good(), None, context)
    assert [op.op for op in ops] == ["create"] and ops[0].note.title == "Credit totals not tracked"

    class Broken:
        async def complete_structured(self, scope, output, **kwargs):
            raise RuntimeError("provider down")

    assert await pe.extract(Broken(), None, context) == []


@pytest.mark.parametrize(
    "said, kind",
    [
        ("mera paisa wapas karo", "refund"),
        ("tum log fraud ho, paisa wapas chahiye", "refund"),
        ("apni raqam wapas do", "refund"),
        ("ab naya account number likh lo payment ke liye: 0123456789", "bank_change"),
        ("Workzap ka naya account number ye hai 0123456789", "bank_change"),
        ("please use this new account for payment", "bank_change"),
    ],
)
def test_roman_urdu_refund_and_changed_bank_details_reach_their_gates(said, kind):
    from app.modules.pi import safety

    assert safety.boundary_asked(said) is not None
    assert safety.boundary_asked(said).value == kind


@pytest.mark.parametrize(
    "said",
    [
        "mere paas naya account number nahi hai",
        "new account opened at my bank for my shop",
        "paise wapas aa gaye the",
        "mera naam Ata hai",
    ],
)
def test_ordinary_sentences_do_not_trip_the_refund_or_bank_gates(said):
    from app.modules.pi import safety

    assert safety.boundary_asked(said) is None


def test_a_third_partys_name_in_roman_urdu_keeps_only_the_role():
    from app.modules.pi import safety

    said = "mere manager ka naam Ahmed Raza hai aur meri biwi ka naam Ayesha hai"
    clean = safety.redact_pii(said)
    assert "Ahmed" not in clean.text and "Ayesha" not in clean.text
    assert "manager ka naam" in clean.text and safety.Pii.NAME in clean.kinds
    own = safety.redact_pii("mera naam Ata hai")
    assert own.text == "mera naam Ata hai"


def test_clothing_shops_are_detected_as_retail_without_stealing_brands_or_fabric():
    found = ip.detect(["I run 3 clothing shops in Dubai and our best sellers keep running out"])
    assert found.primary == "retail_shops_and_chains"
    assert (
        ip.detect(["we have a clothing brand with 3 outlets"]).primary
        == "fashion_and_apparel_brands"
    )
    assert (
        ip.detect(["I sell unstitched lawn fabric"]).primary
        == "unstitched_fabric_lawn_and_textile_retail"
    )


@pytest.mark.parametrize(
    "said",
    [
        "اعطيني حل",
        "أريد حل لهذه المشكلة",
        "ما الحل",
        "کوئی حل بتائیں",
        "مجھے حل چاہیے",
        "hal batao",
    ],
)
def test_arabic_and_urdu_script_requests_for_a_fix_are_recognised(said):
    from app.modules.pi.solution_ask import asked_for_ideas

    assert asked_for_ideas(said), said


def test_arabic_and_urdu_script_how_exactly_is_recognised():
    from app.modules.pi.solution_ask import asked_howto

    for said in ("كيف بالضبط؟", "یہ کیسے ہوگا؟"):
        assert asked_howto(said), said


def test_the_offer_is_not_added_twice():
    from app.modules.pi.solution_ask import already_offers, offer_line

    own = "I can prepare it. Would you like a solution document and a quote for this?"
    assert already_offers(own)
    assert not already_offers("Here are two ideas. Which one first?")
    assert not already_offers(f"Here are two ideas.\n\n{offer_line('en')[:0]}")


def test_word_stems_let_booking_meet_double_book():
    entries = solutions.load("salons_and_barbers")["problems"]
    found = solution_ideas.match_problem(
        entries, "customer_experience_digital", "", "double bookings happen a lot"
    )
    assert found is not None and found["id"] == "p1_booking_appointments"


def test_the_offer_line_exists_in_arabic_and_falls_back_to_english():
    from app.modules.pi.solution_ask import offer_line

    assert "وثيقة" in offer_line("ar")
    assert offer_line("fr").startswith("Shall I get a solution document")
    assert offer_line(None).startswith("Shall I get")
