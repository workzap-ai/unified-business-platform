"""PS-8 context memory: the pure parts (no database): answered_from_records, the owner-language
lines, the implementation wording, the derived scans, correction history, caps and fuzz/timing."""

import json
import random
import string
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.pi import context_memory as cm
from app.modules.pi.context_memory_types import (
    ContextBundle,
    FactItem,
    MessageItem,
    ProblemItem,
    SolutionItem,
    TriedEntry,
)

T, E, C = uuid4(), uuid4(), uuid4()


def bundle(**kw):
    return ContextBundle(tenant_id=T, environment_id=E, customer_id=C, **kw)


def msg(text, n=0):
    return MessageItem(uuid4(), uuid4(), f"2026-10-0{n % 9 + 1}T10:00:00+00:00", text, True)


def fact(key, value, status="owner_said", ref="problem:P1"):
    return FactItem(key, value, status, ref, "P1")


# ---------------------------------------------------------------- answered_from_records


@pytest.mark.parametrize(
    ("asked", "key"),
    [
        ("budget", "budget"),
        ("cost", "budget"),
        ("team", "staff"),
        ("staff", "staff"),
        ("deadline", "deadline"),
        ("when", "deadline"),
        ("where", "location"),
        ("location", "location"),
        ("tools", "tools"),
        ("systems", "tools"),
        ("expected_outcome", "expected_outcome"),
        ("goal", "expected_outcome"),
        ("cause", "cause"),
        ("root cause", "cause"),
    ],
)
def test_a_stored_value_answers_the_question_with_its_source(asked, key):
    b = bundle(facts=(fact(key, "the value", "confirmed"),))
    a = cm.answered_from_records(asked, b)
    assert a is not None and a.value == "the value" and a.ref == "problem:P1"
    assert a.owner_confirmed and a.problem_ref == "P1"


def test_a_pi_guess_or_a_page_read_never_counts_as_answered():
    b = bundle(
        facts=(fact("cause", "late stock", "pi_inferred"), fact("location", "Lahore", "page_read"))
    )
    assert cm.answered_from_records("cause", b) is None
    assert cm.answered_from_records("location", b) is None


def test_owner_said_beats_remembered_and_the_later_problem_wins():
    b = bundle(
        facts=(
            fact("budget", "50k", "owner_said"),
            fact("budget", "old guess", "remembered", "profile:x"),
            fact("budget", "80k", "owner_said"),
        )
    )
    assert cm.answered_from_records("budget", b).value == "80k"
    later_guess = bundle(
        facts=(
            fact("budget", "50k", "owner_said"),
            fact("budget", "guess", "remembered", "profile:x"),
        )
    )
    assert cm.answered_from_records("budget", later_guess).value == "50k"


def test_tried_prefers_stored_over_derived_and_says_when_derived():
    stored = TriedEntry("flyers", "no calls", None, "P2")
    derived = TriedEntry("we tried ads", "", "m1", "", True)
    assert cm.answered_from_records("tried", bundle(tried=(stored, derived))).status == "owner_said"
    only = cm.answered_from_records("tried", bundle(tried=(derived,)))
    assert only.status == "derived" and not only.owner_confirmed
    assert cm.answered_from_records("tried", bundle()) is None


@pytest.mark.parametrize("bad", [None, "", "unknown_key", "BUDGET ", 7, "x" * 10000])
def test_odd_keys_never_raise(bad):
    cm.answered_from_records(bad, bundle(facts=(fact("budget", "1"),)))
    assert cm.answered_from_records(bad, None) is None


def test_an_erased_bundle_answers_nothing():
    assert (
        cm.answered_from_records("budget", bundle(erased=True, facts=(fact("budget", "1"),)))
        is None
    )


# ---------------------------------------------------------------- owner-language lines


@pytest.mark.parametrize("lang", ["en", "roman_ur", "ur", "ar"])
def test_the_known_line_names_what_not_the_values_and_asks_nothing(lang):
    b = bundle(facts=(fact("budget", "SECRET-500"), fact("deadline", "June")))
    line = cm.what_is_already_known(b, lang)
    assert line and "SECRET" not in line and "June" not in line
    assert "?" not in line and "؟" not in line
    assert cm.what_is_already_known(bundle(), lang) == ""


def test_the_known_line_is_in_the_bundle_language_by_default_and_unknown_reads_english():
    b = bundle(language="roman_ur", facts=(fact("budget", "1"),))
    assert "Pehle" in cm.what_is_already_known(b)
    assert cm.what_is_already_known(b, "klingon").startswith("We already have")


def test_normalise_language():
    assert [
        cm.normalise_language(x) for x in ("ur-Latn", "roman urdu", "ur", "ar-SA", None, "fr")
    ] == ["roman_ur", "roman_ur", "ur", "ar", "en", "en"]


# ---------------------------------------------------------------- implementation wording


def sol(ref, impl, stored):
    return SolutionItem("document", ref, impl, stored)


def test_a_proposed_solution_is_never_called_delivered_or_in_progress():
    b = bundle(
        solutions=(sol("SD-0001", "issued", "sent"), sol("Q-0001", "reviewer_approved", "approved"))
    )
    text = cm.implementation_summary(b)
    assert text.startswith("Proposed, not built yet: SD-0001 (sent), Q-0001 (approved).")
    assert "In progress" not in text and "Delivered" not in text
    assert not any(s.implemented or s.in_progress for s in b.solutions)


def test_three_groups_and_exact_states_in_every_language():
    b = bundle(
        solutions=(
            sol("A", "issued", "sent"),
            SolutionItem("build", "chat:1", "in_build", "S13_IN_BUILD"),
            sol("C", "delivered", "delivered"),
        )
    )
    for lang in ("en", "roman_ur", "ur", "ar"):
        out = cm.implementation_summary(b, lang)
        assert "A (sent)" in out and "chat:1 (S13_IN_BUILD)" in out and "C (delivered)" in out
    assert cm.implementation_summary(bundle()) == ""
    assert (
        cm.implementation_summary(bundle(erased=True, solutions=(sol("A", "issued", "sent"),)))
        == ""
    )


def test_paid_and_accepted_are_still_proposed_not_built():
    s = (sol("Q", "paid", "confirmed"), sol("R", "accepted", "accepted"))
    out = cm.implementation_summary(bundle(solutions=s))
    assert out.startswith("Proposed, not built yet") and "Delivered" not in out


# ---------------------------------------------------------------- derived scans


@pytest.mark.parametrize(
    "text",
    [
        "no thanks, not interested in that",
        "Mujhe yeh nahi chahiye",
        "iski zaroorat nahi hai",
        "یہ نہیں چاہیے",
        "لا أريد هذا",
        "We don't want a new app",
    ],
)
def test_rejection_cues_in_four_languages(text):
    found = cm.scan_rejections((msg(text),))
    assert len(found) == 1 and found[0].derived and found[0].ref.startswith("msg:")


@pytest.mark.parametrize("text", ["I want it", "yes please", "nowhere near", "snow thanks"])
def test_no_false_rejection(text):
    assert cm.scan_rejections((msg(text),)) == ()


def test_tried_cues_and_negation():
    got = cm.scan_tried(
        (msg("we tried posting on facebook"), msg("maine try kiya tha"), msg("we never tried it"))
    )
    assert len(got) == 2 and all(t.derived for t in got)
    assert [t.what for t in got][0] == "maine try kiya tha"  # newest first


# ---------------------------------------------------------------- history, rows, bundle views


def revision(problem_id, rev, diff, reason="correction", by="person"):
    return SimpleNamespace(
        problem_id=problem_id,
        revision=rev,
        diff=diff,
        reason=reason,
        by=by,
        created_at=datetime(2026, 10, rev, tzinfo=UTC),
    )


def test_correction_history_keeps_every_prior_value_with_the_correcting_message():
    pid = uuid4()
    rows = [
        revision(
            pid, 1, {"constraints": [None, {"budget": {"text": "30k", "msg": "m1"}}]}, "created"
        ),
        revision(
            pid,
            2,
            {
                "constraints": [
                    {"budget": {"text": "30k", "msg": "m1"}},
                    {"budget": {"text": "50k", "msg": "m2"}},
                ]
            },
        ),
        revision(
            pid,
            3,
            {
                "constraints": [
                    {"budget": {"text": "50k", "msg": "m2"}},
                    {"budget": {"text": "70k", "msg": "m3"}},
                ]
            },
        ),
        revision(
            pid,
            4,
            {"title": ["Stock late", "Stock runs out"], "source_message_ids": [["a"], ["a", "m9"]]},
        ),
    ]
    now = {pid: {"constraints.budget": {"text": "70k", "msg": "m3"}, "title": "Stock runs out"}}
    out, cut = cm._revision_corrections(rows, {pid: "P1"}, now, 10)
    assert not cut
    budget = next(c for c in out if c.field == "constraints.budget")
    assert budget.current == {"text": "70k", "msg": "m3"}
    assert [p.value["text"] for p in budget.prior] == [
        "30k",
        "50k",
    ]  # first fill is not a correction
    assert [p.msg for p in budget.prior] == ["m2", "m3"]
    assert not any(c.field == "source_message_ids" for c in out)
    title = next(c for c in out if c.field == "title")
    assert title.prior[0].value == "Stock late" and title.prior[0].msg == "m9"


def test_correction_cap_sets_truncated_and_malformed_diffs_are_ignored():
    pid = uuid4()
    rows = [
        revision(pid, 1, {f"f{i}": ["a", "b"] for i in range(5)}),
        revision(pid, 2, "garbage"),
        revision(pid, 3, {"x": "notapair", "y": [1]}),
    ]
    out, cut = cm._revision_corrections(rows, {pid: "P1"}, {}, 3)
    assert len(out) == 3 and cut


def test_problem_row_with_malformed_columns_reads_as_not_said():
    row = SimpleNamespace(
        id=uuid4(),
        number=2,
        title="  Late   stock ",
        status="confirmed",
        category="stock_inventory",
        summary=None,
        subtype=None,
        conversation_id=None,
        user_words=["a", 5, None],
        systems_mentioned="oops",
        scope="bad",
        frequency=None,
        since={"text": "x" * 500},
        impact=[],
        trigger=None,
        current_workaround=None,
        who_notices=None,
        person_believes_cause=None,
        requested_solution=None,
        severity_stated=None,
        source_message_ids=None,
        revision=None,
        constraints="junk",
        tried={"a": 1},
        cause=[],
        expected_outcome=7,
    )
    p = cm._problem_item(row, True)
    assert (
        p.title == "Late stock"
        and p.ref == "P2"
        and p.user_words == ("a",)
        and p.systems_mentioned == ()
    )
    assert p.budget is None and p.tried == () and p.cause_text == "" and p.expected_outcome == ""
    assert len(p.since["text"]) <= 200 and p.revision == 1
    assert cm._problem_item(row, False).tried == ()


def test_facts_from_problems_keep_a_pi_guess_apart():
    p = ProblemItem(
        id=uuid4(),
        number=1,
        title="t",
        status="confirmed",
        category="c",
        cause_text="late truck",
        cause_status="pi_inferred",
        expected_outcome="no stockouts",
        systems_mentioned=("Excel", "POS"),
        scope={"where": "Lahore shop"},
    )
    facts = cm.facts_from_problems((p,))
    by = {f.key: f for f in facts}
    assert by["cause"].status == "pi_inferred" and not by["cause"].owner_confirmed
    assert by["tools"].value == "Excel, POS" and by["location"].value == "Lahore shop"
    assert by["expected_outcome"].owner_confirmed


def test_known_records_shape_order_and_json_safety():
    b = bundle(
        conversation_id=uuid4(),
        facts=(fact("budget", "50k"),),
        messages=(msg("hello"),),
        solutions=(sol("SD-0001", "issued", "sent"),),
        rejections=(cm.scan_rejections((msg("no thanks"),))[0],),
    )
    recs = b.known_records()
    assert [r["source"] for r in recs] == ["facts", "solutions", "rejections", "messages"]
    for r in recs:
        assert set(r) == {
            "source",
            "text",
            "kind",
            "status",
            "ref",
            "tenant_id",
            "environment_id",
            "customer_id",
            "conversation_id",
        }
        assert r["tenant_id"] == str(T) and r["customer_id"] == str(C)
    assert next(r for r in recs if r["source"] == "rejections")["status"] == "derived"
    json.dumps(recs)
    json.dumps(b.to_dict())
    assert cm.known_records(None) == []


def test_two_bundles_never_share_state():
    a = bundle(facts=(fact("budget", "1"),))
    b = bundle()
    assert cm.answered_from_records("budget", b) is None and cm.answered_from_records("budget", a)


# ---------------------------------------------------------------- fuzz and timing


def test_fuzz_scans_and_readers_never_raise():
    rng = random.Random(8)
    alphabet = string.printable + "نہیں چاہیے لا أريد ضرورت " + "‮\u0000\U0001f600"
    for _ in range(300):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 300)))
        ms = (msg(text),)
        cm.scan_rejections(ms)
        cm.scan_tried(ms)
        b = bundle(messages=ms, facts=(fact(rng.choice(["budget", text[:5]]), text),))
        cm.answered_from_records(rng.choice(list(cm.ANSWER_KEYS)), b)
        cm.what_is_already_known(b, rng.choice(["en", "ur", text[:3]]))
        cm.implementation_summary(b)
        b.known_records()
        b.to_dict()


def test_scans_are_linear_on_hostile_text():
    hostile = ("no thanks " * 5000, "a" * 200000, "i " * 100000, " ".join(["we tried"] * 20000))
    start = time.perf_counter()
    for text in hostile:
        cm.scan_rejections((msg(text),))
        cm.scan_tried((msg(text),))
    assert time.perf_counter() - start < 2.0


def test_five_thousand_messages_scan_quickly():
    ms = tuple(msg(f"message number {i} about stock and orders") for i in range(5000))
    start = time.perf_counter()
    cm.scan_rejections(ms)
    cm.scan_tried(ms)
    assert time.perf_counter() - start < 2.0


def test_safe_caps_and_redacts_defensively():
    assert len(cm._safe("word " * 1000, 50)) <= 50
    assert cm._safe(None, 10) == "" and cm._safe(5, 10) == ""
    assert "4111111111111111" not in cm._safe("my card 4111 1111 1111 1111 ok", 100)


def test_summary_lists_at_most_five_items_per_group():
    many = tuple(sol(f"D{i}", "issued", "sent") for i in range(9))
    out = cm.implementation_summary(bundle(solutions=many))
    assert "D4 (sent)" in out and "D5" not in out


def test_message_items_are_oldest_first_and_flag_the_cap():
    rows = [
        SimpleNamespace(
            id=uuid4(),
            conversation_id=C,
            created_at=datetime(2026, 10, d, tzinfo=UTC),
            body=f"m{d}",
            message_type="text",
        )
        for d in (5, 4, 3)  # the query returns newest first, one more than the cap
    ]
    items, cut = cm._message_items(rows, 2, 50, True)
    assert [m.text for m in items] == ["m4", "m5"] and cut
    items, cut = cm._message_items(rows[:2], 2, 50, False)
    assert not cut and not any(m.current for m in items)
