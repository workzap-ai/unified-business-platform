# ruff: noqa: E501
"""Controlled execution: second-audit fixes. Approval grammar, forgery, screening, replay, survivors (dry run, pure)."""

import dataclasses
import hashlib
import time
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.pi import execution_audit as au
from app.modules.pi import execution_scope as xs
from app.modules.pi import execution_task as xt
from app.modules.pi.execution_scope import (
    ApprovalCue,
    ApprovedScope,
    classify_approval,
    create_scope,
    scope_sha,
)
from app.modules.pi.execution_task import (
    ActionApproval,
    ActionRequest,
    Evidence,
    RecoveryRecord,
    RollbackPlan,
    Task,
    TaskState,
    action_sha,
    approve_task,
    check_can_execute,
    fail_task,
    mark_performed,
    new_task,
    rollback_task,
    start_task,
)

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
TEXT = "Update the delivery note template on the staging site."
TOOLS = ["read_record", "write_note", "send_message", "publish_live", "delete_record"]
LIMITS = {"max_actions": 5, "max_messages": 1, "max_units": 5}
PLAN = RollbackPlan(
    ("restore the saved template",), True, "Ali (staff)", "template shows the old text"
)
EV = (Evidence("order:1", "order_status", "Omar (staff)"),)


def mk(**over):
    args = dict(
        scope_text=TEXT,
        tools=TOOLS,
        limits=LIMITS,
        expires_at=NOW + timedelta(days=2),
        approver="Sara (owner)",
        approval_source="owner_chat",
        approval_text="I approve this",
        referenced_sha=None,
        task_owner="Ali (staff)",
        task_creator="Zed (staff)",
        now=NOW,
    )
    args.update(over)
    if args["referenced_sha"] is None:
        args["referenced_sha"] = scope_sha(
            args["scope_text"], frozenset(args["tools"]), args["limits"]
        )
    return create_scope(**args)


def sc_task(tools=TOOLS, limits=LIMITS):
    sc = mk(tools=tools, limits=limits).scope
    t = new_task(
        id="t1",
        title="T",
        owner="Ali (staff)",
        creator="Zed (staff)",
        scope_sha=sc.scope_sha,
        rollback=PLAN,
    ).task
    t = approve_task(t, sc, NOW).task
    return sc, t


# ---- HIGH 1: approval grammar ----

FALSE_YES = [
    "'go ahead'",
    "they say go ahead",
    "ijazat hai kal",
    "अनुमति है कल",
    "GO AHEAD (just kidding)",
    "he approved",
    "approved by Ali",
    "we approved earlier",
    "approved yesterday",
    "go ahead as long as it is free",
    "go ahead depending on price",
    "go ahead on the condition that it is free",
    "go ahead in case it is ok",
    "go ahead assuming it is cheap",
    "go ahead except payment",
    "I guess go ahead",
    "go ahead whenever",
    "kar do warna",
    "go ahead next week",
    "approved for now",
    "go ahead tonight",
    "approved before friday",
    "go ahead on monday",
    "kar do kal",
    "منظور ہے کل",
    "شروع کریں کل",
    "शुरू करो कल",
    "موافق غدا",
    "موافق لاحقا",
    "should I go ahead",
    "whether to go ahead",
    "I might go ahead",
    "we cannot proceed",
    "I approve nothing",
    "I confirm nothing",
    "my boss wants you to go ahead",
    "he asked me to proceed",
    "I approve a much bigger scope",
    "go ahead with something else",
    "go ahead with deleting everything",
    "I approve 4111111111111111",
    "I approve and also pay 500",
    "approve: delete all",
    "go ahead 👍",
    "go ahead (staging)",
    "I approve; also send it to everyone",
    'say "go ahead"',
    "it's a go ahead from him",
    "should we proceed?",
    "do you approve?",
    "never approve",
    "approve karo nahi",
    "I approve it but",
]


@pytest.mark.parametrize("t", FALSE_YES)
def test_audit_strings_are_not_approval(t):
    assert classify_approval(t) is not ApprovalCue.EXPLICIT_YES
    assert not mk(approval_text=t).ok


TRUE_YES = [
    "I approve",
    "I approve this",
    "approved",
    "Approved.",
    "go ahead",
    "Yes, go ahead",
    "Please go ahead",
    "please proceed",
    "proceed",
    "yes please proceed",
    "I confirm",
    "confirmed",
    "you may proceed",
    "I authorise this",
    "I authorize it",
    "approve this scope",
    "Go ahead, thanks",
    "thank you, go ahead sir",
    "yes I approve the plan",
    "OK go ahead",
    "sure, go ahead",
    "do it",
    "approval given",
    "haan kar do",
    "ji haan kar do",
    "manzoor hai",
    "main approve karta hoon",
    "shuru karo",
    "approve hai",
    "ijazat hai",
    "ji kar dein",
    "منظور ہے",
    "ہاں کر دو",
    "جی منظور ہے",
    "شروع کریں",
    "میں منظوری دیتا ہوں",
    "اجازت ہے",
    "हाँ कर दो",
    "मंजूर है",
    "मंज़ूर है",
    "शुरू करो",
    "अनुमति है",
    "मैं मंजूरी देती हूं",
    "जी हाँ मंजूर है",
    "أوافق",
    "موافق",
    "نعم، تفضل",
    "أنا أوافق",
    "تمت الموافقة",
    "اعتمد",
]


def test_true_yes_count():
    assert len(TRUE_YES) >= 35


@pytest.mark.parametrize("t", TRUE_YES)
def test_true_yes_still_pass(t):
    assert classify_approval(t) is ApprovalCue.EXPLICIT_YES
    assert mk(approval_text=t).ok


@pytest.mark.parametrize(
    "t", ["ok", "theek hai", "haan", "sure", "hmm", "yes", "ji", "ٹھیک ہے", "ठीक है", "حسنا"]
)
def test_bare_vague_words_stay_vague(t):
    assert classify_approval(t) is ApprovalCue.VAGUE


def test_every_apostrophe_and_quote_style_is_quoted():
    for q in ["'", '"', "‘", "’", "“", "”", "«", "»", "`"]:
        assert classify_approval(f"{q}go ahead{q}") is ApprovalCue.QUOTED


def test_contraction_is_not_a_quote():
    assert classify_approval("don't proceed") is ApprovalCue.NEGATIVE


def test_grammar_requires_exactly_one_core_and_only_fillers():
    assert classify_approval("approve approve") is not ApprovalCue.EXPLICIT_YES
    assert classify_approval("go ahead and delete") is not ApprovalCue.EXPLICIT_YES
    assert (
        classify_approval("yes yes yes yes yes yes yes go ahead") is not ApprovalCue.EXPLICIT_YES
    )  # filler cap
    assert classify_approval("go ahead " + "x" * 200) is not ApprovalCue.EXPLICIT_YES  # length cap


def test_per_action_approval_uses_same_grammar():
    sc, t = sc_task()
    a = ActionRequest("send_message", {"text": "hi"})

    def ap(text):
        return ActionApproval(
            action_sha(a), "Sara (owner)", text, NOW - timedelta(minutes=1), "ap-1"
        )

    assert check_can_execute(
        t, sc, NOW, action=a, action_approval=ap("I approve this action")
    ).allowed
    for bad in (
        "they say go ahead",
        "go ahead on monday",
        "approved by Ali",
        "'go ahead'",
        "I approve 4111111111111111",
    ):
        assert not check_can_execute(t, sc, NOW, action=a, action_approval=ap(bad)).allowed


# ---- HIGH 2: forgery ----


def _unkeyed(parts):
    import json

    return hashlib.sha256(json.dumps(parts, default=str).encode()).hexdigest()


def forged_scope(**over):
    good = mk().scope
    fields = dict(
        scope_text=TEXT,
        tools=frozenset({"send_email"}),
        limits=(("max_actions", 99),),
        expires_at=NOW + timedelta(days=9999),
        approver="evil",
        approval_source="owner_chat",
        approved_at=NOW,
        scope_sha=good.scope_sha,
        cue_sha="0" * 64,
        task_owner="Ali (staff)",
        task_creator="Zed (staff)",
        seal="x",
    )
    fields.update(over)
    return ApprovedScope(**fields)


def test_directly_built_scope_is_not_intact_and_cannot_approve():
    f = forged_scope()
    assert not f.is_intact()
    t = new_task(
        id="t1",
        title="T",
        owner="Ali (staff)",
        creator="Zed (staff)",
        scope_sha=f.scope_sha,
        rollback=PLAN,
    ).task
    assert not approve_task(t, f, NOW).ok
    f2 = dataclasses.replace(f, seal=_unkeyed([f.scope_sha]))
    assert not f2.is_intact() and not approve_task(t, f2, NOW).ok


def test_scope_with_stolen_key_still_fails_sanity_checks():
    # even a correctly keyed seal does not make an insane scope pass at use
    for over in (
        dict(approver="Ali (staff)"),
        dict(approver="pi"),
        dict(approver="ａｌｉ (staff)"),
        dict(expires_at=NOW + timedelta(days=9999)),
        dict(expires_at=NOW + timedelta(days=30, seconds=5)),
        dict(expires_at=NOW),
        dict(tools=frozenset({"take_payment"})),
        dict(tools=frozenset({"nope"})),
        dict(tools=frozenset()),
        dict(approval_source="forwarded"),
        dict(limits=(("max_actions", -1),)),
        dict(limits=(("max_actions", True),)),
    ):
        base = forged_scope(
            **{
                "approver": "Sara (owner)",
                "tools": frozenset({"read_record"}),
                "expires_at": NOW + timedelta(days=2),
                **over,
            }
        )
        base = dataclasses.replace(
            base, scope_sha=xs.scope_sha(base.scope_text, base.tools, dict(base.limits))
        )
        sealed = dataclasses.replace(base, seal=xs._seal(base))
        assert not sealed.is_intact(), over
    ok = forged_scope(
        approver="Sara (owner)",
        tools=frozenset({"read_record"}),
        expires_at=NOW + timedelta(days=30),
    )
    ok = dataclasses.replace(ok, scope_sha=xs.scope_sha(ok.scope_text, ok.tools, dict(ok.limits)))
    assert dataclasses.replace(ok, seal=xs._seal(ok)).is_intact()  # the sane control case passes


def test_is_live_enforces_max_validity_and_start():
    sc = mk().scope
    object.__setattr__(sc, "expires_at", NOW + timedelta(days=9999))
    assert not sc.is_live(NOW)
    sc2 = mk().scope
    assert sc2.is_live(NOW) and not sc2.is_live(NOW - timedelta(seconds=1))


def test_hand_built_task_is_refused_by_gate_and_functions():
    sc, good = sc_task()
    hand = Task(
        id="t1",
        title="T",
        owner="Ali (staff)",
        creator="Zed (staff)",
        scope_sha=sc.scope_sha,
        state=TaskState.RUNNING,
        rollback=PLAN,
        approved_by="Sara (owner)",
    )
    assert not check_can_execute(hand, sc, NOW).allowed
    assert not check_can_execute(
        dataclasses.replace(hand, seal=_unkeyed(["task"])), sc, NOW
    ).allowed
    assert not start_task(
        dataclasses.replace(good, state=TaskState.APPROVED, seal="nope"), sc, NOW
    ).ok
    # editing any field of a genuine task invalidates it
    for over in (
        dict(state=TaskState.RUNNING),
        dict(owner="evil"),
        dict(approved_by="evil"),
        dict(scope_sha="1" * 64),
        dict(rollback=None),
        dict(depends_on=("x",)),
    ):
        assert not check_can_execute(dataclasses.replace(good, **over), sc, NOW).allowed
    assert check_can_execute(good, sc, NOW).allowed


def test_task_approved_under_another_scope_is_refused():
    sc, t = sc_task()
    other = mk(approver="Dana (owner)").scope
    assert other.scope_sha == sc.scope_sha
    d = check_can_execute(t, other, NOW)
    assert not d.allowed


def test_scope_for_other_owner_is_refused():
    sc = mk(task_owner="Someone Else").scope
    t = new_task(
        id="t1",
        title="T",
        owner="Ali (staff)",
        creator="Zed (staff)",
        scope_sha=sc.scope_sha,
        rollback=PLAN,
    ).task
    assert not approve_task(t, sc, NOW).ok


# ---- MEDIUM ----


def test_identity_comparison_is_nfkc_casefold():
    assert not mk(approver="ｏｍａｒ", task_owner="omar").ok
    assert not mk(approver="OMAR  ", task_owner="omar").ok
    assert not mk(approver="Omar", task_creator="ｏｍａｒ").ok
    assert not mk(approver="Ｐｉ").ok


@pytest.mark.parametrize(
    "over",
    [
        dict(task_owner=None),
        dict(task_creator=None),
        dict(task_owner=""),
        dict(task_creator="pi"),
        dict(task_owner=5),
    ],
)
def test_owner_and_creator_are_required(over):
    assert not mk(**over).ok


CARDS = [
    "4111.1111.1111.1111",
    "4111/1111/1111/1111",
    "4111_1111_1111_1111",
    "4111 1111 1111 1111",
    "4111​1111​1111​1111",
    "4111  1111  1111  1111",
    "4111 - 1111 - 1111 - 1111",
    "4111111111111111",
    "٤١١١١١١١١١١١١١١١",
    "４１１１１１１１１１１１１１１１",
    "4111, 1111, 1111, 1111",
]
SECRETS = [
    "my password is hunter2",
    "otp 123456",
    "cvv is 123",
    "pin 1234",
    "Password: abc",
    "میرا پاسورڈ abc",
    "मेरा पासवर्ड abc",
    "كلمة المرور abc",
    "one time code 55",
    "card number please",
    "ओटीपी 12",
    "اوٹی پی 1",
]


@pytest.mark.parametrize("v", CARDS + SECRETS)
def test_param_screening_catches_obfuscated_card_and_secret_values(v):
    sc, t = sc_task()
    d = check_can_execute(t, sc, NOW, action=ActionRequest("write_note", {"note": v}))
    assert not d.allowed and d.code == "bad_params"
    assert not check_can_execute(
        t, sc, NOW, action=ActionRequest("write_note", {"note": ["x", {"deep": v}]})
    ).allowed


@pytest.mark.parametrize(
    "v",
    [
        "Update order 1234 for delivery on 12 March",
        "call 0300 1234567 tomorrow",
        "ref 2026-11-01 batch 77",
        "hello",
    ],
)
def test_param_screening_allows_ordinary_text(v):
    sc, t = sc_task()
    assert check_can_execute(t, sc, NOW, action=ActionRequest("write_note", {"note": v})).allowed


@pytest.mark.parametrize("v", CARDS)
def test_audit_redacts_obfuscated_numbers(v):
    e = au.AuditLog().append(
        at=NOW, kind="action", actor="a", task_id="t", detail=f"paid with {v} ok"
    )
    assert "411" not in e.detail and "[number]" in e.detail


def test_audit_redacts_other_pii_and_secrets():
    log = au.AuditLog()

    def d(x):
        return log.append(at=NOW, kind="action", actor="a", task_id="t", detail=x).detail

    assert "123456789012" not in d("id 123456789012")
    assert "0300" not in d("phone 0300-1234567") and "0300" not in d("phone 0300 123 4567")
    for e in (
        "ali @ example.com",
        "ali (at) example (dot) com",
        "ali@example.com",
        "ali [at] example [dot] com",
    ):
        out = d(f"mail {e} now")
        assert "example" not in out, out
    for s in ("password is hunter2", "my otp 123456", "cvv is 123", "پاسورڈ abc", "पासवर्ड abc"):
        out = d(s)
        assert "hunter2" not in out and "123" not in out and "abc" not in out, out
    assert d("plain note about delivery") == "plain note about delivery"


def test_audit_append_junk_kind_never_raises():
    log = au.AuditLog()
    for k in ([], {}, None, 5, b"action", ("action",), object()):
        assert log.append(at=NOW, kind=k, actor="a", task_id="t") is None
    assert log.entries == ()
    assert log.append(at=NOW, kind="action", actor=object(), task_id=None) is not None


def test_replayed_action_approval_is_refused():
    sc, t = sc_task()
    a = ActionRequest("send_message", {"text": "hi"})
    ap = ActionApproval(
        action_sha(a), "Sara (owner)", "I approve this action", NOW - timedelta(minutes=1), "ap-1"
    )
    assert check_can_execute(t, sc, NOW, action=a, action_approval=ap).allowed
    assert check_can_execute(
        t, sc, NOW, action=a, action_approval=ap, consumed_approvals=set()
    ).allowed
    assert check_can_execute(
        t, sc, NOW, action=a, action_approval=ap, consumed_approvals={"other"}
    ).allowed
    assert not check_can_execute(
        t, sc, NOW, action=a, action_approval=ap, consumed_approvals={"ap-1"}
    ).allowed
    assert not check_can_execute(
        t, sc, NOW, action=a, action_approval=ap, consumed_approvals=["ap-1"]
    ).allowed
    assert not check_can_execute(
        t, sc, NOW, action=a, action_approval=ap, consumed_approvals=5
    ).allowed
    noid = dataclasses.replace(ap, approval_id="")
    assert not check_can_execute(t, sc, NOW, action=a, action_approval=noid).allowed


def test_action_approver_must_be_independent_of_owner_and_creator():
    sc, t = sc_task()
    a = ActionRequest("send_message", {"text": "hi"})
    for who in ("Ali (staff)", "Zed (staff)", "ｚｅｄ (staff)", "pi"):
        ap = ActionApproval(
            action_sha(a), who, "I approve this action", NOW - timedelta(minutes=1), "ap-1"
        )
        assert not check_can_execute(t, sc, NOW, action=a, action_approval=ap).allowed


# ---- survivors ----


def test_destructive_needs_own_approval():
    sc, t = sc_task()
    a = ActionRequest("delete_record", {"id": "r1"})
    d = check_can_execute(t, sc, NOW, action=a)
    assert not d.allowed and d.code == "needs_approval"
    ap = ActionApproval(
        action_sha(a), "Sara (owner)", "I approve this action", NOW - timedelta(minutes=1), "ap-9"
    )
    assert check_can_execute(t, sc, NOW, action=a, action_approval=ap).allowed
    assert xs.NEEDS_OWN_APPROVAL == {"irreversible", "destructive", "outbound_message"}


def _ap(a, i="ap-1"):
    return ActionApproval(
        action_sha(a), "Sara (owner)", "I approve this action", NOW - timedelta(minutes=1), i
    )


def test_max_messages_is_required_and_capped():
    a = ActionRequest("send_message", {"text": "hi"})
    sc, t = sc_task(limits={"max_actions": 5})
    d = check_can_execute(t, sc, NOW, action=a, action_approval=_ap(a))
    assert not d.allowed and "max_messages" in d.reasons[0]
    sc, t = sc_task()
    assert check_can_execute(t, sc, NOW, action=a, action_approval=_ap(a)).allowed
    assert not check_can_execute(
        t, sc, NOW, action=a, action_approval=_ap(a), used={"messages": 1}
    ).allowed
    two = ActionRequest("send_message", {"text": "hi"}, 2)
    assert not check_can_execute(t, sc, NOW, action=two, action_approval=_ap(two)).allowed
    # a non-message tool is not capped by max_messages
    w = ActionRequest("write_note", {"note": "x"}, 2)
    assert check_can_execute(t, sc, NOW, action=w, used={"messages": 9}).allowed


def test_max_actions_required_for_any_action():
    sc, t = sc_task(limits={"max_units": 5})
    assert not check_can_execute(t, sc, NOW, action=ActionRequest("write_note", {"n": "x"})).allowed


def test_limit_range_and_types():
    assert mk(limits={"max_actions": 0}).ok
    assert mk(limits={"max_actions": 1_000_000}).ok
    for bad in (1_000_001, -1, True, False, 1.0, "5", None):
        assert not mk(limits={"max_actions": bad}).ok
    assert not mk(limits={"": 1}).ok
    assert not mk(limits={"a" * 121: 1}).ok
    assert not mk(limits={f"k{i}": 1 for i in range(21)}).ok
    assert mk(limits={f"k{i}": 1 for i in range(20)}).ok


def test_thirty_day_boundary():
    assert mk(expires_at=NOW + timedelta(days=30)).ok
    assert not mk(expires_at=NOW + timedelta(days=30, seconds=5)).ok
    assert mk(expires_at=NOW + timedelta(seconds=1)).ok
    assert not mk(expires_at=NOW).ok


def test_notes_reasons_and_recovery_evidence():
    sc, t = sc_task()
    r = start_task(t, sc, NOW).task
    for bad in ("", "   ", None, 5, "x" * 2001):
        assert not mark_performed(r, bad).ok
    v = mark_performed(r, "edited").task
    assert v.state is TaskState.VERIFYING
    for bad in ("", "  ", None, "x" * 2001):
        assert not fail_task(r, bad).ok
    f = fail_task(r, "broke").task
    for kind in ("model_statement", "", "chat_claim"):
        assert not rollback_task(
            f, RecoveryRecord("old text back", (Evidence("r", kind, "Ali (staff)"),), "Ali (staff)")
        ).ok
    assert not rollback_task(
        f, RecoveryRecord("old text back", (Evidence("", "file", "Ali (staff)"),), "Ali (staff)")
    ).ok
    assert not rollback_task(
        f, RecoveryRecord("old text back", (Evidence("r", "file", "assistant"),), "Ali (staff)")
    ).ok
    assert not rollback_task(
        f, RecoveryRecord("old text back", (Evidence("r", "file", "Ali (staff)"),), "")
    ).ok
    assert not rollback_task(f, RecoveryRecord("   ", EV, "Ali (staff)")).ok
    assert rollback_task(f, RecoveryRecord("old text back", EV, "Ali (staff)")).ok


def test_audit_digest_covers_every_field():
    def one(**kw):
        base = dict(at=NOW, kind="action", actor="a", task_id="t", detail="d")
        base.update(kw)
        return au.AuditLog().append(**base).hash

    h = one()
    assert one(at=NOW + timedelta(seconds=1)) != h
    assert one(kind="refusal") != h
    assert one(actor="b") != h
    assert one(task_id="u") != h
    assert one(detail="e") != h
    log = au.AuditLog()
    log.append(at=NOW, kind="action", actor="a", task_id="t")
    e2 = log.append(at=NOW, kind="action", actor="a", task_id="t")
    assert e2.hash != log.entries[0].hash
    es = list(log.entries)
    forged = dataclasses.replace(es[0], at=(NOW + timedelta(days=1)).isoformat())
    assert (
        not au.verify_chain([forged, es[1]]).ok and au.verify_chain([forged, es[1]]).bad_index == 0
    )


def _rehash(e, **kw):
    e = dataclasses.replace(e, **kw)
    return dataclasses.replace(
        e, hash=au._digest(e.seq, e.at, e.kind, e.actor, e.task_id, e.detail, e.prev_hash)
    )


def test_verify_chain_seq_kind_and_link_checks_individually():
    log = au.AuditLog()
    for _ in range(3):
        log.append(at=NOW, kind="action", actor="a", task_id="t")
    es = list(log.entries)
    v = au.verify_chain([es[0], _rehash(es[1], seq=5), es[2]])
    assert not v.ok and v.bad_index == 1 and "sequence" in v.reason
    v = au.verify_chain([es[0], _rehash(es[1], kind="bogus"), es[2]])
    assert not v.ok and v.bad_index == 1 and "kind" in v.reason
    v = au.verify_chain([es[0], _rehash(es[1], prev_hash="f" * 64), es[2]])
    assert not v.ok and v.bad_index == 1 and "previous" in v.reason
    v = au.verify_chain([es[0], dataclasses.replace(es[1], detail="x"), es[2]])
    assert not v.ok and v.bad_index == 1 and "hash" in v.reason
    assert au.verify_chain(es).ok


def test_audit_scaling_after_screening():
    log = au.AuditLog()
    t0 = time.perf_counter()
    for i in range(20_000):
        log.append(at=NOW, kind="action", actor="a", task_id="t", detail=f"step {i} done")
    assert time.perf_counter() - t0 < 10.0
    t0 = time.perf_counter()
    for _ in range(200):
        au._clean("x" * 500 + " 4111 1111 1111 1111 " * 5, 500)
    assert time.perf_counter() - t0 < 5.0


def test_seal_key_env_is_used(monkeypatch):
    monkeypatch.setenv("PI_EXECUTION_SEAL_KEY", "k" * 16)
    assert xs._load_key() == b"k" * 16
    monkeypatch.setenv("PI_EXECUTION_SEAL_KEY", "short")
    assert len(xs._load_key()) == 32 and xs._load_key() != xs._load_key()


def test_gate_still_never_raises_on_junk():
    sc, t = sc_task()
    junk = [None, 0, "x", object(), [], {}, float("nan"), Task]
    for a in junk:
        for b in junk:
            assert check_can_execute(a, b, NOW).allowed is False
            assert check_can_execute(t, b, NOW, action=a, consumed_approvals=a).allowed is False
        assert (
            check_can_execute(
                t, sc, NOW, action=ActionRequest("send_message", {}), action_approval=a
            ).allowed
            is False
        )
    assert xt.check_can_execute(t, sc, NOW).allowed
