# ruff: noqa: E501
"""PS-flow journeys, pure part (no database, no model): 32 scripted business journeys in English,
Roman Urdu, Urdu script and Arabic (`tests/fixtures/ps_flow_journeys.json`).

Each journey is checked at the points where the flow decides something, against behaviour only:
the fixture's own text (one question, last; reply language; British spelling; no price or promise;
no repeated question), the L2-1 gate over the owner's stated limits, the blueprint over the folded
record (traceable, limits and figures kept, corrections applied, nothing priced, a guess labelled
as one, deterministic), and the decision gates (vague replies are never a yes).

`xfail(strict=False)` marks behaviour the lanes have not landed yet, each with its reason; the test
flips to a pass when the behaviour lands. Findings the flow lead should read are listed in the
reasons (search "FINDING").
"""

from collections import Counter

import pytest

from app.modules.pi import decisions
from app.modules.pi.flow import State
from tests.support import ps_journey_checks as ck
from tests.support import ps_journey_flow as fl

JOURNEYS = ck.load()
BY_ID = {j["id"]: j for j in JOURNEYS}
IDS = [j["id"] for j in JOURNEYS]
NON_LATIN = ("ur", "ar")

LOCALISED = (
    "constraint_check word rules read English and Roman Urdu only (its docstring); an Urdu or "
    "Arabic idea that breaks a limit is 'unknown', so the blueprint can recommend it: localised "
    "constraint check not landed"
)


def ideas_of(journey, must):
    return [(n, i) for n, i in enumerate(journey["ideas"]) if i["must"] in must]


def case(journey_id, n, reason=None):
    marks = [pytest.mark.xfail(reason=reason, strict=False)] if reason else []
    return pytest.param(journey_id, n, marks=marks, id=f"{journey_id}-{n}")


# --- the fixture itself ----------------------------------------------------------------------


def test_the_suite_is_big_and_varied_enough():
    assert len(JOURNEYS) >= 30
    assert len(IDS) == len(set(IDS))
    languages = Counter(j["language"] for j in JOURNEYS)
    assert set(languages) == set(ck.LANGUAGES)
    assert all(count >= 6 for count in languages.values()), languages
    types = Counter(d for j in JOURNEYS for d in j["difficulty"])
    assert set(types) <= set(ck.DIFFICULTY), set(types) - set(ck.DIFFICULTY)
    assert all(types[d] >= 3 for d in ck.DIFFICULTY), types
    assert len({j["industry"] for j in JOURNEYS}) >= 13, sorted({j["industry"] for j in JOURNEYS})
    required = {
        "rental", "ecommerce", "booking", "banquet", "healthcare", "salon", "repair",
        "agriculture_poultry", "agriculture_dairy", "agriculture_crops", "trucking", "school",
        "gym", "pharmacy", "restaurant",
    }  # fmt: skip
    assert required <= {j["industry"] for j in JOURNEYS}


@pytest.mark.parametrize("journey_id", IDS)
def test_a_journey_is_well_formed_and_quotes_the_owner(journey_id):
    j = BY_ID[journey_id]
    assert j["language"] in ck.LANGUAGES and j["difficulty"] and len(j["turns"]) >= 3
    assert j["ideas"] and any(i["must"] == "not_rejected" for i in j["ideas"])
    assert j["approval"]["vague"] and j["approval"]["yes"]
    for n, turn in enumerate(j["turns"]):
        assert turn["owner"].strip() and turn["pi"].strip()
        for op in turn["ops"]:
            note = op["note"]
            for words in (note.get("user_words") or [], note.get("cause_words") or []):
                assert all(w in turn["owner"] for w in words), (n, words)
            for key in fl.LIMIT_KEYS:
                assert not note.get(key) or note[key] in turn["owner"], (n, key)
            for text in note.get("cannot_change") or []:
                assert text in turn["owner"], (n, text)
            for tried in note.get("tried") or []:
                assert tried["what"] in turn["owner"], (n, tried)
            if note.get("cause_said"):  # a said cause carries the owner's own words as evidence
                assert note.get("cause_words"), n
    for idea in j["ideas"]:
        assert idea["must"] in ("reject", "not_rejected", "unknown", "generic")
        assert (idea["must"] == "generic") == (not idea["refs"]), idea  # unrelated = no problem
    if j["rerank"]:
        assert j["rerank"]["after_turn"] < len(j["turns"])


@pytest.mark.parametrize("journey_id", IDS)
def test_the_scripted_record_keeps_every_figure_with_corrections_applied(journey_id):
    j = BY_ID[journey_id]
    kept, gone = ck.figures_after_corrections(j)
    record = " ".join(
        " ".join([*p["quotes"], p["where"], p["how_often"], p["money"], *p["limits"].values()])
        for p in fl.fold_record(j)
    )
    for figure in kept:
        assert ck.has_figure(record, figure), (figure, record)
    for figure in gone:
        assert not ck.has_figure(record, figure), (figure, record)
    assert len(fl.fold_record(j)) == j["expect"]["problems"]


@pytest.mark.parametrize("journey_id", IDS)
def test_the_scripted_record_keeps_limits_tried_and_a_cause_with_the_right_status(journey_id):
    j = BY_ID[journey_id]
    expect = j["expect"]
    problems = fl.fold_record(j)
    data = fl.requirements_data(problems)
    limits = expect.get("limits") or {}
    for key in fl.LIMIT_KEYS:
        if limits.get(key):
            assert any(limits[key] in text for text in data.get(key, [])), (key, data)
    for sub in limits.get("cannot") or []:
        assert any(sub in text for text in data.get("cannot_change", [])), (sub, data)
    for key in limits.get("absent") or []:
        assert not data.get(key if key != "budget" else "budget"), (key, data)
    for sub in expect.get("tried") or []:
        assert any(sub in t["what"] for t in data.get("tried", [])), (sub, data)
    cause = expect.get("cause")
    if cause:
        said = problems[cause["problem"]]["cause"]
        assert said and said["status"] == cause["status"]
        if said["status"] == "owner_said":
            assert said["words"]  # the owner's own words stand behind it
    else:
        assert not any(p["cause"] for p in problems)  # pi's guess is never an owner cause


# --- pi's replies ----------------------------------------------------------------------------


@pytest.mark.parametrize("journey_id", IDS)
def test_every_reply_asks_one_question_and_it_is_last(journey_id):
    for n, reply in enumerate(ck.pi_replies(BY_ID[journey_id])):
        assert ck.one_question_last(reply), (n, reply)


@pytest.mark.parametrize("journey_id", IDS)
def test_every_reply_is_in_the_owners_language(journey_id):
    j = BY_ID[journey_id]
    for n, reply in enumerate(ck.pi_replies(j)):
        assert ck.language_matches(j["language"], reply), (n, ck.detect_language(reply), reply)
    assert all(ck.language_matches(j["language"], t) for t in ck.owner_texts(j))


@pytest.mark.parametrize("journey_id", IDS)
def test_english_replies_use_british_spelling(journey_id):
    j = BY_ID[journey_id]
    for reply in ck.pi_replies(j):
        assert not ck.american_spelling(reply), reply


@pytest.mark.parametrize("journey_id", IDS)
def test_no_reply_prices_or_promises(journey_id):
    for n, reply in enumerate(ck.pi_replies(BY_ID[journey_id])):
        assert not ck.money_or_promise(reply), (n, reply)


@pytest.mark.parametrize("journey_id", IDS)
def test_no_question_repeats_and_none_asks_what_was_already_said(journey_id):
    j = BY_ID[journey_id]
    assert ck.repeated_questions(ck.pi_replies(j)) == []
    assert ck.asked_again(j) == []
    assert j["turns"][0]["pi"].count("pi") >= 1  # the first message says what pi is


# --- the gate over the owner's stated limits -----------------------------------------------------


def gate_cases(*musts, rule=None):
    out = []
    for j in JOURNEYS:
        for n, idea in ideas_of(j, musts):
            out.append(case(j["id"], n, rule(j, idea) if rule else None))
    return out


def reject_pending(j, idea):
    if j["language"] in NON_LATIN:
        return LOCALISED
    if j["id"] == "clinic_roman_ur" and idea.get("limit") == "tried_failed":
        return (
            "FINDING a Roman Urdu outcome 'mix ho gaye' (what the owner tried, it failed) is not "
            "read as a failure, so the same idea is 'unknown' instead of rejected"
        )
    return None


def check(journey_id, n):
    j = BY_ID[journey_id]
    data = fl.requirements_data(fl.fold_record(j))
    return j["ideas"][n], fl.verdict(j["ideas"][n]["text"], data, j["language"])


@pytest.mark.parametrize(("journey_id", "n"), gate_cases("reject", rule=reject_pending))
def test_an_idea_that_breaks_a_stated_limit_is_rejected(journey_id, n):
    idea, v = check(journey_id, n)
    assert v.status == "violates", (idea, v)
    assert v.rule in (idea.get("limit"), "cannot_change", "budget", "tried_failed")


@pytest.mark.parametrize(("journey_id", "n"), gate_cases("reject"))
def test_an_idea_that_breaks_a_limit_is_never_reported_as_satisfied(journey_id, n):
    _, v = check(journey_id, n)
    assert v.status in ("violates", "unknown"), v


def unknown_pending(j, idea):
    if idea.get("limit") == "missing_budget":
        return (
            "FINDING no budget was stated and the idea clearly costs money: the gate says 'ok' "
            "(nothing to break) where the brief wants 'unknown' (never shown as satisfied)"
        )
    return None


@pytest.mark.parametrize(("journey_id", "n"), gate_cases("unknown", rule=unknown_pending))
def test_a_limit_that_cannot_be_checked_is_shown_unknown_never_satisfied(journey_id, n):
    _, v = check(journey_id, n)
    assert v.status == "unknown", v


def voice_cases():
    out = []
    for j in JOURNEYS:
        pending = fl.pending_components(j)
        for component in fl.VOICE_COMPONENTS:
            marks = (
                [pytest.mark.xfail(reason=pending[component], strict=False)]
                if component in pending
                else []
            )
            out.append(pytest.param(j["id"], component, marks=marks, id=f"{j['id']}-{component}"))
    return out


@pytest.mark.parametrize(("journey_id", "component"), voice_cases())
def test_the_chat_gates_every_idea_once_through_the_one_verdict_path(journey_id, component):
    """option_voice.voice: a violating idea is removed, an unrelated one is removed, a valid idea
    in other words stays, an unchecked one is labelled, one question last, the pick is a clear idea."""
    found = fl.voice_findings(BY_ID[journey_id])
    assert found[component] == [], found[component]


# --- the blueprint over the folded record (PS-4, blueprint_wire.build) ----------------------------


BP_CASES = [
    pytest.param(
        j["id"],
        c,
        marks=(
            [pytest.mark.xfail(reason=fl.pending_components(j)[c], strict=False)]
            if c in fl.pending_components(j)
            else []
        ),
        id=f"{j['id']}-{c}",
    )
    for j in JOURNEYS
    for c in fl.COMPONENTS
    if c != "rerank" or j["rerank"]
]


@pytest.mark.parametrize(("journey_id", "component"), BP_CASES)
def test_the_blueprint_is_ready_clean_and_honest(journey_id, component):
    j = BY_ID[journey_id]
    found = fl.blueprint_findings(j, fl.synthetic_views(j), fl.synthetic_owner_messages(j))
    assert found[component] == [], found[component]


SAME_CASES = [
    pytest.param(
        j["id"],
        marks=[pytest.mark.xfail(reason=fl.SAME_OPTION, strict=False)]
        if j["id"] in ("repair_ar", "booking_ur") or "corrections" in j["difficulty"]
        else [],
        id=j["id"],
    )
    for j in JOURNEYS
]


@pytest.mark.parametrize("journey_id", SAME_CASES)
def test_the_same_option_leads_the_chat_pick_and_the_document_blueprint(journey_id):
    """Through the real option_voice.voice and brain_docs.apply_box (the document builder)."""
    assert fl.same_option_findings(BY_ID[journey_id]) == []


# --- the decision gates --------------------------------------------------------------------------


def facts_for(j, **extra):
    problems = fl.fold_record(j)
    refs = [f"P{n}" for n in range(1, len(problems) + 1)]
    base = {
        "message_id": "m-yes",
        "can_approve": True,
        "problem_count": len(problems),
        "group_count": len({p["category"] for p in problems}),
        "problem_refs": refs,
        "brief": {},
        "changed": False,
    }
    return {**base, **extra}


def starts_quote(decision):
    return bool(decision and "request_solution" in decision.effects)


def vague_cases():
    out = []
    for j in JOURNEYS:
        for reply in j["approval"]["vague"]:
            marks: list = []
            out.append(pytest.param(j["id"], reply, marks=marks, id=f"{j['id']}-{reply}"))
    return out


@pytest.mark.parametrize(("journey_id", "reply"), vague_cases())
def test_a_vague_reply_to_the_offer_is_never_a_yes(journey_id, reply):
    j = BY_ID[journey_id]
    decision = decisions.decide(State.S5_READINESS, reply, j["language"], facts_for(j))
    assert not starts_quote(decision), (reply, decision)
    assert decision is None or decision.next_state != State.S6_PREPARING


@pytest.mark.parametrize("journey_id", IDS)
def test_an_explicit_yes_is_the_only_thing_that_starts_the_quote(journey_id):
    j = BY_ID[journey_id]
    facts = facts_for(j)
    decision = decisions.decide(State.S5_READINESS, j["approval"]["yes"], j["language"], facts)
    assert decision is not None, j["approval"]["yes"]
    if facts["group_count"] >= 2:  # the offer is for the whole set: ask which, start nothing yet
        assert not starts_quote(decision) and decision.brief.get("scope_asked")
    else:
        assert starts_quote(decision)
        assert decision.next_state == State.S6_PREPARING
        assert decision.brief["offer"]["problem_refs"] == facts["problem_refs"]
    for effect in decision.effects:
        assert effect == "request_solution"  # never a payment, a price or a booking


@pytest.mark.parametrize("journey_id", [j["id"] for j in JOURNEYS if j["approval"].get("scope")])
def test_the_exact_scope_is_approved_and_a_vague_reply_to_the_scope_question_is_not(journey_id):
    j = BY_ID[journey_id]
    scope = j["approval"]["scope"]
    facts = facts_for(j)
    assert facts["group_count"] >= 2
    asked = decisions.decide(State.S5_READINESS, j["approval"]["yes"], j["language"], facts)
    assert asked and asked.brief.get("scope_asked") and not starts_quote(asked)
    brief = {"scope_asked": True, "offer_yes_id": "m-yes"}
    vague = decisions.decide(
        State.S5_READINESS, "hmm", j["language"], facts_for(j, brief=brief, message_id="m-vague")
    )
    assert not starts_quote(vague)
    chosen = decisions.decide(
        State.S5_READINESS,
        scope["choose"],
        j["language"],
        facts_for(j, brief=brief, chosen_refs=["P1"], message_id="m-scope"),
    )
    assert starts_quote(chosen)
    assert chosen.brief["offer"]["problem_refs"] == ["P1"]  # only what was approved


@pytest.mark.parametrize("language", ck.LANGUAGES)
def test_r1_starts_the_quote_only_and_r3_ready_to_buy_does_not(language):
    j = next(x for x in JOURNEYS if x["language"] == language)
    r1 = decisions.decide(
        State.S3_NOTED, "send me the quote", language, facts_for(j, buying_signal="R1")
    )
    assert starts_quote(r1) and r1.effects == ["request_solution"]
    r3 = decisions.decide(State.S3_NOTED, "ok", language, facts_for(j, buying_signal="R3"))
    assert not starts_quote(r3)


@pytest.mark.parametrize(
    "said", ["theek hai", "haan", "ji", "yes", "sure", "ٹھیک ہے", "ہاں", "نعم"]
)
def test_the_spec_yes_words_are_a_yes(said):
    """ROFFER03 (docs/pi-saas/spec-text/pi-platform-spec-v1.6-2026-10-30.txt:1832) lists yes/haan/ji/
    theek hai/okay go ahead/sure as yes. A bare 'ok' is left out of the vague list's expectations
    only because the same spec lists 'ok' in its yes classifier (v1.6:3666): owner decision open."""
    answer, confidence = decisions.classify(said)
    assert answer == decisions.Answer.YES and confidence >= decisions.YES_AT
