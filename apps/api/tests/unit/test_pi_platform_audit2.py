"""Live Audit 2 fixes (platform spec, Book 4): a direct ask for the document is a yes, Roman Urdu
stays neutral and polite, and an impatient owner is apologised to in one word."""

import pytest

from app.modules.pi import constitution
from app.modules.pi import decisions as d
from app.modules.pi.flow import State as S


def _facts(**more):
    return {"message_id": "m1", "can_approve": True, "problem_count": 2, "group_count": 2,
            "problem_refs": ["a1", "b2"], "brief": {}, **more}  # fmt: skip


@pytest.mark.parametrize(
    "said",
    [
        "dain solution document mujhay",
        "Solution document bhejein",
        "quote do",
        "send me the document",
        "Yes please, prepare the document and the quote.",
        "Haan document aur quote bana dein.",
        "can I get the quote",
        "نعم، جهزوا المستند وعرض السعر من فضلكم.",
    ],
)
def test_a_direct_ask_for_the_document_is_recognised(said):
    assert d.asks_for_document(said)


@pytest.mark.parametrize(
    "said",
    [
        "how much will the quote be?",
        "document ka kitna charge hai",
        "I don't want the document",
        "document nahi chahiye",
        "send the document later",
        "what does the document cover?",
        "Menu ka taste roz alag hota hai",
    ],
)
def test_prices_refusals_and_questions_about_it_are_not_a_request(said):
    assert not d.asks_for_document(said)


@pytest.mark.parametrize("state", [S.S1_LISTENING, S.S3_NOTED, S.S4_SORTED_SUMMARY, S.S5_READINESS])
def test_the_ask_is_a_yes_from_any_listening_step_and_covers_everything_noted(state):
    decision = d.decide(state, "dain solution document mujhay", "roman_ur", _facts())
    assert decision is not None and decision.next_state == S.S6_PREPARING
    assert "request_solution" in decision.effects
    assert decision.brief["offer"]["problem_refs"] == ["a1", "b2"]
    assert "?" not in (decision.reply or "")  # the confirmation asks nothing (G28)


def test_the_ask_with_two_groups_skips_the_all_or_some_question():
    decision = d.decide(
        S.S5_READINESS, "Yes please, prepare the document and the quote.", "en", _facts()
    )
    assert decision is not None and decision.next_state == S.S6_PREPARING


def test_a_bare_yes_to_the_offer_still_asks_all_or_some():
    decision = d.decide(S.S5_READINESS, "yes", "en", _facts())
    assert decision is not None and decision.next_state is None and decision.brief["scope_asked"]


def test_nothing_noted_means_nothing_to_prepare():
    assert d.decide(S.S1_LISTENING, "send me the quote", "en", _facts(problem_count=0)) is None


def test_a_team_member_asking_gets_the_decision_maker_line_in_any_listening_step():
    decision = d.decide(S.S3_NOTED, "send me the quote", "en", _facts(can_approve=False))
    assert decision is not None and decision.next_state is None


def test_an_answer_to_all_or_some_is_not_swallowed_by_the_direct_ask():
    facts = _facts(brief={"scope_asked": True}, chosen_refs=["a1"])
    decision = d.decide(S.S5_READINESS, "only the first one, send the document", "en", facts)
    assert decision is not None and decision.brief["offer"]["problem_refs"] == ["a1"]


def _lint(reply, said="", language="roman_ur"):
    ctx = {"reply_language": language, "latest_customer_message": said,
           "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
           "flow": {"state": "S5_READINESS"}}  # fmt: skip
    return {v.rule for v in constitution.lint(reply, ctx)}


@pytest.mark.parametrize(
    "bad", ["Samajh gaya, aur kya masla hai?", "Main bhejunga.", "Main bata sakta hoon."]
)
def test_gendered_first_person_urdu_is_flagged(bad):
    assert "R-GEN-01" in _lint(bad)


def test_neutral_forms_pass():
    assert "R-GEN-01" not in _lint("Maine note kar liya. Baat samajh aa gayi. Bhej diya jayega.")


def test_the_informal_imperative_is_flagged_and_the_aap_form_is_not():
    assert "R-TONE-04" in _lint("Is hafte ginti note karo.")
    assert "R-TONE-04" not in _lint("Is hafte ginti note karein aur list rakhein.")


def test_words_the_owner_used_first_are_not_corrected_back_at_them():
    assert "R-GEN-01" not in _lint("Aap ne kaha samajh gaya.", said="mujhe samajh gaya")
    assert "R-TONE-04" not in _lint("Aap ka 'karo' ka matlab?", said="ye karo")


def test_a_known_wrong_spelling_is_flagged():
    assert "R-SPELL-01" in _lint("Is par ghoor karein.")
    assert "R-SPELL-01" not in _lint("Is par ghaur karein.")


def test_the_urdu_rules_apply_to_roman_urdu_only():
    assert not {"R-GEN-01", "R-TONE-04", "R-SPELL-01"} & _lint("Please karo it", language="en")


def test_maazrat_as_an_opener_is_not_a_stiff_apology():
    assert "R-VOICE-04" not in _lint("Maazrat, ye raha.", said="kab se pooch raha hoon")
    assert "R-VOICE-04" in _lint("Mujhe maazrat chahiye.", said="kab se pooch raha hoon")


@pytest.mark.parametrize(
    "said",
    [
        "It takes me two hours to prepare a quote for each client",
        "I send my customers a quote every day and they ignore it",
        "I need to send documents to the customs office",
        "Customer ko quote bhejna parta hai aur wo ghalat nikalta hai",
        "Ek aur company ne proposal bheja hai",
        "Let me send you the proposal I got from another vendor",
        "What does the document do for my staff problem?",
        "Which document do you mean?",
        "How do you prepare the document?",
        "Will you send the quote here or by email?",
        "Document kaun banata hai?",
        "Quote kab tak bhejenge?",
        "mujhe quote nhi chahiye",
        "no need to send the quote",
        "مجھے کوٹیشن نہیں چاہیے",
    ],
)
def test_a_problem_or_a_question_or_a_refusal_that_mentions_the_document_is_not_the_ask(said):
    assert not d.asks_for_document(said)
    assert d.decide(S.S3_NOTED, said, "en", _facts()) is None


def test_the_direct_confirmation_never_carries_the_reminder_question():
    facts = _facts(ask_consent=True)
    decision = d.decide(S.S3_NOTED, "send me the quote", "en", facts)
    assert decision is not None and "?" not in decision.reply


def test_polite_questions_that_are_requests_still_count():
    assert d.asks_for_document("Can you send me the quote?")
    assert d.asks_for_document("could you prepare the document and the quote")


def test_more_gendered_forms_are_caught_and_ordinary_words_are_not():
    for bad in (
        "Main aap ki baat note karta hoon.",
        "Main bhejunga.",
        "Kal dunga.",
        "Main dekh lunga.",
    ):
        assert "R-GEN-01" in _lint(bad), bad
    assert "R-GEN-01" not in _lint("Lungi aur chungi ka hisaab alag likhein.")


def test_bold_or_quoted_pi_text_is_not_a_way_around_the_tone_rules():
    assert "R-GEN-01" in _lint("*Samajh gaya*, aur kya masla hai?")
    assert "R-GEN-01" not in _lint("Aap ne likha *samajh gaya* theek hai.", said="samajh gaya")


def test_no_stored_workzap_sentence_uses_a_tool_word_and_every_problem_has_a_first_question():
    from app.modules.pi import solutions

    for key in solutions.industries():
        for problem in solutions.load(key)["problems"]:
            build = (problem.get("workzap_build") or {}).get("text", "")
            assert not solutions.banned_tool_words(build), (key, problem["id"])
            assert (problem.get("ask_first") or "").strip().endswith("?"), (key, problem["id"])
