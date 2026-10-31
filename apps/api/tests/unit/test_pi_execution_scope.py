# ruff: noqa: E501
"""Controlled execution: approved scope, approval cues (dry run, pure)."""

import time
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.pi.execution_scope import (
    ApprovalCue,
    ApprovedScope,
    classify_approval,
    create_scope,
    scope_sha,
)

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
TEXT = "Update the delivery note template on the staging site."
TOOLS = ["read_record", "write_note"]
LIMITS = {"max_actions": 5}


def make(**over):
    args = dict(
        scope_text=TEXT,
        tools=TOOLS,
        limits=LIMITS,
        expires_at=NOW + timedelta(days=2),
        approver="Sara (owner)",
        approval_source="owner_chat",
        approval_text="I approve this",
        referenced_sha=scope_sha(TEXT, frozenset(TOOLS), LIMITS),
        task_owner="Ali (staff)",
        now=NOW,
    )
    args.update(over)
    return create_scope(**args)


def test_baseline_creates_scope():
    r = make()
    assert (
        r.ok and isinstance(r.scope, ApprovedScope) and r.scope.is_intact() and r.scope.is_live(NOW)
    )


YES = [
    "I approve",
    "approved",
    "Yes, go ahead",
    "please proceed",
    "haan kar do",
    "ji haan kar do",
    "manzoor hai",
    "main approve karta hoon",
    "منظور ہے",
    "ہاں کر دو",
    "हाँ कर दो",
    "मंजूर है",
    "أوافق",
    "موافق",
    "نعم، تفضل",
]


@pytest.mark.parametrize("t", YES)
def test_explicit_yes(t):
    assert classify_approval(t) is ApprovalCue.EXPLICIT_YES


VAGUE = [
    "ok",
    "okay",
    "hmm",
    "maybe",
    "sure",
    "theek hai",
    "thik hai",
    "yes",
    "haan",
    "ji",
    "ٹھیک ہے",
    "ठीक है",
    "حسنا",
    "let me think",
    "",
    "   ",
    "👍",
]


@pytest.mark.parametrize("t", VAGUE)
def test_vague_never_approves(t):
    assert classify_approval(t) not in (ApprovalCue.EXPLICIT_YES,)
    assert not make(approval_text=t).ok


NEG = [
    "don't proceed",
    "do not proceed",
    "I do not approve",
    "not approved",
    "haan kar do nahi",
    "nahi, kar do",
    "mat karo, kar do",
    "never go ahead",
    "stop, proceed later",
    "نہیں منظور ہے",
    "منظور نہیں",
    "नहीं मंजूर है",
    "لا اوافق",
    "dont approve",
    "DON’T proceed",
    "wait, I approve",
]


@pytest.mark.parametrize("t", NEG)
def test_negation_blocks(t):
    assert classify_approval(t) is not ApprovalCue.EXPLICIT_YES
    assert not make(approval_text=t).ok


COND = [
    "I approve if the price stays",
    "approved but only on staging",
    "go ahead once Ali checks",
    "agar sasta ho to kar do",
    "kar do lekin kal",
    "I approve?",
    "approved؟",
    "go ahead tomorrow",
    "شاید منظور ہے",
    "अगर सस्ता हो तो मंजूर है",
    "اوافق بشرط",
]


@pytest.mark.parametrize("t", COND)
def test_conditional_or_question_blocks(t):
    assert classify_approval(t) is not ApprovalCue.EXPLICIT_YES


QUOTED = [
    '"I approve"',
    "> I approve",
    "He said I approve",
    "Fwd: I approve",
    "forwarded: approved",
    "unhone kaha manzoor hai",
    "“go ahead”",
    "قال اوافق",
    "«موافق»",
    "Ali wrote: approved",
]


@pytest.mark.parametrize("t", QUOTED)
def test_quoted_or_forwarded_blocks(t):
    assert classify_approval(t) is ApprovalCue.QUOTED
    assert not make(approval_text=t).ok


def test_non_string_and_huge_cue_fail_closed():
    for bad in (None, 5, b"approved", ["approved"], "approved " + "x" * 2000):
        assert classify_approval(bad) is ApprovalCue.UNKNOWN
        assert not make(approval_text=bad).ok


def test_approval_only_for_exact_scope_text():
    for changed in (TEXT + " ", TEXT.replace("staging", "production"), TEXT.upper(), TEXT + "​"):
        # the approval referenced the hash of TEXT, not of the changed text
        assert not make(scope_text=changed).ok
    assert not make(tools=["read_record", "write_note", "send_message"]).ok
    assert not make(limits={"max_actions": 6}).ok
    assert not make(referenced_sha="0" * 64).ok
    assert not make(referenced_sha=None).ok


@pytest.mark.parametrize(
    "over",
    [
        dict(scope_text=""),
        dict(scope_text="x" * 20_001),
        dict(tools=[]),
        dict(tools=None),
        dict(tools=["nope"]),
        dict(tools=["take_payment"]),
        dict(tools=["store_card"]),
        dict(tools=["request_password"]),
        dict(tools=["request_otp"]),
        dict(tools=[1]),
        dict(limits=None),
        dict(limits={"a": -1}),
        dict(limits={"a": True}),
        dict(limits={"a": 1.5}),
        dict(expires_at=NOW),
        dict(expires_at=NOW - timedelta(days=1)),
        dict(expires_at=NOW + timedelta(days=31)),
        dict(expires_at=datetime(2026, 11, 2)),
        dict(expires_at="tomorrow"),
        dict(approver=""),
        dict(approver="pi"),
        dict(approver="Model"),
        dict(approver="ali (staff)"),
        dict(approval_source="forwarded"),
        dict(approval_source=None),
        dict(now=datetime(2026, 11, 1)),
        dict(now=None),
    ],
)
def test_each_guard_alone_refuses(over):
    r = make(**over)
    assert not r.ok and r.scope is None and r.reasons


def test_tampered_scope_is_detected():
    s = make().scope
    object.__setattr__(s, "scope_text", TEXT + " and delete everything")
    assert not s.is_intact()
    s2 = make().scope
    object.__setattr__(s2, "expires_at", NOW + timedelta(days=300))
    assert not s2.is_intact()


def test_scope_expires():
    s = make().scope
    assert s.is_live(NOW + timedelta(days=1, hours=23))
    assert not s.is_live(NOW + timedelta(days=2))
    assert not s.is_live(datetime(2026, 11, 1))


@pytest.mark.parametrize("n", [1_000, 10_000, 100_000])
def test_huge_input_is_fast_and_refused(n):
    big = "I approve " * n
    t0 = time.perf_counter()
    assert classify_approval(big) is ApprovalCue.UNKNOWN
    assert not make(scope_text=big).ok
    assert not make(approval_text=big).ok
    assert time.perf_counter() - t0 < 1.0


def test_max_size_cue_scales_linearly():
    a = "word " * 150
    b = "word " * 190
    t0 = time.perf_counter()
    for _ in range(200):
        classify_approval(a + "kar do")
    t1 = time.perf_counter()
    for _ in range(200):
        classify_approval(b + "kar do")
    t2 = time.perf_counter()
    assert (t2 - t1) < (t1 - t0) * 3 + 0.05
