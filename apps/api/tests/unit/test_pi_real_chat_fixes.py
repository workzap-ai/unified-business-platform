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
    assert reply_voice.localise_noted(en, "en") == en
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
