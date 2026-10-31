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

import importlib.util
import json
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
THEEK_HAI = (
    "FINDING decisions.YES_WORDS counts a bare 'theek hai' / 'ٹھیک ہے' / 'تمام' as an explicit yes "
    "(classify gives YES 0.97, decide() starts the quote); the brief says only a plain yes counts "
    "and 'ok', 'hmm', 'maybe', 'theek hai' alone are not approval"
)
VAGUE_YES = {"theek hai", "ٹھیک ہے", "تمام"}


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


@pytest.mark.parametrize(("journey_id", "n"), gate_cases("unknown"))
def test_an_unknown_idea_is_labelled_not_checked_when_shown(journey_id, n):
    from app.modules.pi import option_wiring

    j = BY_ID[journey_id]
    data = fl.requirements_data(fl.fold_record(j))
    wired = option_wiring.gate_ideas([j["ideas"][n]["text"]], option_wiring.requirements_from(data))
    for text in wired.unknown:
        assert any(option_wiring.NOT_CHECKED in s for s in wired.shown if text.rstrip(". ") in s)


@pytest.mark.parametrize(("journey_id", "n"), gate_cases("not_rejected"))
def test_a_valid_idea_in_other_words_is_not_rejected_for_not_repeating_the_owner(journey_id, n):
    idea, v = check(journey_id, n)
    owner = " ".join(ck.owner_texts(BY_ID[journey_id])).casefold()
    assert v.status != "violates", (idea, v)
    assert idea["text"].casefold() not in owner  # different wording from the owner's


@pytest.mark.parametrize(
    "journey_id", [j["id"] for j in JOURNEYS if any(i["must"] == "generic" for i in j["ideas"])]
)
@pytest.mark.xfail(
    reason="PS-3 idea relevance is not landed: nothing flags an unrelated generic idea before the "
    "blueprint (module app.modules.pi.idea_relevance does not exist)",
    strict=False,
)
def test_an_unrelated_generic_idea_is_flagged_generic_before_it_is_shown(journey_id):
    assert importlib.util.find_spec("app.modules.pi.idea_relevance") is not None


@pytest.mark.parametrize("journey_id", IDS)
def test_when_every_idea_is_left_out_there_is_one_targeted_question(journey_id):
    from app.modules.pi import option_wiring

    j = BY_ID[journey_id]
    data = fl.requirements_data(fl.fold_record(j))
    rejected = [i["text"] for i in j["ideas"] if i["must"] == "reject"]
    wired = option_wiring.gate_ideas(rejected, option_wiring.requirements_from(data), j["language"])
    if wired.question:
        assert wired.question.count("?") == 1 and wired.question.endswith("?")
        assert not wired.accepted
    assert not wired.accepted or j["language"] in NON_LATIN or not rejected or wired.rejected


# --- the blueprint over the folded record ---------------------------------------------------------


def findings(journey_id, upto=None):
    j = BY_ID[journey_id]
    views = fl.synthetic_views(j, upto)
    owner = fl.synthetic_owner_messages(j)
    bp = fl.build_blueprint(j, views, owner)
    return j, views, bp, fl.blueprint_findings(j, bp, views)


STRICT = (
    "traceable",
    "generic_never_recommended",
    "figures",
    "limits",
    "no_price_or_promise",
    "causes_labelled",
)


def blueprint_cases():
    out = []
    for j in JOURNEYS:
        for component in STRICT:
            out.append(pytest.param(j["id"], component, id=f"{j['id']}-{component}"))
        if any(i["must"] == "reject" for i in j["ideas"]):
            marks = (
                [pytest.mark.xfail(reason=LOCALISED, strict=False)]
                if j["language"] in NON_LATIN
                else []
            )
            out.append(
                pytest.param(
                    j["id"], "violating_never_recommended", marks=marks, id=f"{j['id']}-violating"
                )
            )
        if any(i.get("limit") == "missing_budget" for i in j["ideas"]):
            out.append(
                pytest.param(
                    j["id"],
                    "unknown_never_clear",
                    marks=pytest.mark.xfail(
                        reason="FINDING no budget stated: a costly idea is checked 'ok' and shown "
                        "as clear of the limits, not as not yet checked",
                        strict=False,
                    ),
                    id=f"{j['id']}-unknown",
                )
            )
        if any(i.get("limit") == "budget" for i in j["ideas"]) and j["language"] not in NON_LATIN:
            out.append(
                pytest.param(
                    j["id"],
                    "risk_quotes_owner_limit",
                    marks=pytest.mark.xfail(
                        reason="FINDING blueprint_doc.issues() reports 'holds a price or saving' "
                        "for the risk 'Step n clashes with what you said: it goes past the budget "
                        "you gave (\"Rs 50,000\")': it only quotes the owner's own budget, yet "
                        "every over-budget rejection makes issues() non-empty",
                        strict=False,
                    ),
                    id=f"{j['id']}-risk-quotes-budget",
                )
            )
        if "corrections" in j["difficulty"]:
            out.append(
                pytest.param(
                    j["id"],
                    "evidence_survives_correction",
                    marks=pytest.mark.xfail(
                        reason="FINDING blueprint_doc.options() verifies a problem's first three "
                        "quote words against its FIRST source message; after a corrected figure "
                        "the quote holds the new figure ('550') that message never had, the "
                        "evidence fails and the blueprint says 'learn more first' for a problem "
                        "the owner described clearly",
                        strict=False,
                    ),
                    id=f"{j['id']}-evidence-after-correction",
                )
            )
    return out


@pytest.mark.parametrize(("journey_id", "component"), blueprint_cases())
def test_the_blueprint_is_traceable_checked_and_honest(journey_id, component):
    _, _, _, found = findings(journey_id)
    assert found[component] == [], found[component]


@pytest.mark.parametrize("journey_id", IDS)
def test_the_blueprint_and_the_recommendation_are_the_same_on_two_runs(journey_id):
    first = findings(journey_id)[2]
    second = findings(journey_id)[2]
    assert json.dumps(first, sort_keys=True, ensure_ascii=False) == json.dumps(
        second, sort_keys=True, ensure_ascii=False
    )


@pytest.mark.parametrize("journey_id", IDS)
def test_the_recommendation_names_a_checked_idea_or_asks_to_learn_more(journey_id):
    j, _, bp, _ = findings(journey_id)
    rec = bp["recommendation"]
    steps = {s["text"]: s for s in bp["steps"]}
    if rec["learn_first"]:
        assert rec["option"] and "Learn" in rec["option"]
        return
    assert rec["option"] in steps
    assert steps[rec["option"]]["linked"]
    assert steps[rec["option"]]["check"]["status"] != "violates"


def rerank_cases():
    out = []
    for j in JOURNEYS:
        if j["rerank"]:
            marks = (
                [pytest.mark.xfail(reason=LOCALISED, strict=False)]
                if j["language"] in NON_LATIN
                else []
            )
            out.append(pytest.param(j["id"], marks=marks, id=j["id"]))
    return out


@pytest.mark.parametrize("journey_id", rerank_cases())
def test_a_changed_requirement_reranks_and_rejects_the_earlier_recommendation(journey_id):
    j = BY_ID[journey_id]
    rr = j["rerank"]
    before = findings(journey_id, rr["after_turn"])[2]
    after = findings(journey_id)[2]
    idea = j["ideas"][rr["idea"]]["text"]
    assert idea not in [r["option"] for r in before["recommendation"]["rejected"]]
    assert fl.recommended_idea(j, after) != rr["idea"]
    assert idea in [r["option"] for r in after["recommendation"]["rejected"]]
    if fl.recommended_idea(j, before) == rr["idea"]:  # it led before: something else leads now
        assert after["recommendation"]["option"] != idea


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
            marks = (
                [pytest.mark.xfail(reason=THEEK_HAI, strict=False)] if reply in VAGUE_YES else []
            )
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
