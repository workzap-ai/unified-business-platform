# ruff: noqa: E501
"""Controlled execution: task state machine, DAG, bounded authority, gate, audit chain (dry run, pure)."""

import dataclasses
import time
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.pi import execution_audit as au
from app.modules.pi.execution_scope import ApprovedScope, create_scope, scope_sha
from app.modules.pi.execution_task import (
    ActionApproval,
    ActionRequest,
    Evidence,
    RecoveryRecord,
    RollbackPlan,
    TaskState,
    Verification,
    action_sha,
    approve_task,
    check_can_execute,
    complete_task,
    fail_task,
    mark_performed,
    new_task,
    record_decision,
    rollback_task,
    start_task,
    validate_dag,
)

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
TEXT = "Update the delivery note template on the staging site."
TOOLS = ["read_record", "write_note", "send_message", "publish_live"]
LIMITS = {"max_actions": 3, "max_messages": 1, "max_units": 5}
PLAN = RollbackPlan(
    ("restore the saved template",), True, "Ali (staff)", "template shows the old text"
)
EV = (Evidence("order:123", "order_status", "Omar (staff)"),)


def scope(**over):
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
    r = create_scope(**args)
    assert r.ok, r.reasons
    return r.scope


def task(sc=None, **over):
    sc = sc or scope()
    args = dict(
        id="t1",
        title="Update template",
        owner="Ali (staff)",
        creator="Zed (staff)",
        scope_sha=sc.scope_sha,
        rollback=PLAN,
    )
    args.update(over)
    r = new_task(**args)
    assert r.ok, r.reasons
    return r.task


def approved(sc=None):
    sc = sc or scope()
    r = approve_task(task(sc), sc, NOW)
    assert r.ok, r.reasons
    return sc, r.task


def running():
    sc, t = approved()
    r = start_task(t, sc, NOW)
    assert r.ok, r.reasons
    return sc, r.task


def verification(**over):
    args = dict(
        acceptance_id="a1",
        acceptance_statement="template shows the new text",
        evidence=EV,
        passed=True,
        verifier="Omar (staff)",
    )
    args.update(over)
    return Verification(**args)


# ---- state machine ----

ALL = list(TaskState)
LEGAL = {
    ("proposed", "approved"),
    ("approved", "running"),
    ("running", "verifying"),
    ("running", "failed"),
    ("verifying", "done"),
    ("verifying", "failed"),
    ("failed", "rolled_back"),
}


def test_full_happy_path_and_done_only_via_verification():
    sc, t = running()
    t = mark_performed(t, "template edited").task
    assert t.state is TaskState.VERIFYING
    r = complete_task(t, verification())
    assert r.ok and r.task.state is TaskState.DONE and r.task.verification


def _drivers(sc, t):
    """Every transition function tried against a task in each state; only LEGAL pairs may succeed."""
    return {
        "approved": lambda x: approve_task(x, sc, NOW),
        "running": lambda x: start_task(x, sc, NOW),
        "verifying": lambda x: mark_performed(x, "note"),
        "done": lambda x: complete_task(x, verification()),
        "failed": lambda x: fail_task(x, "broke"),
        "rolled_back": lambda x: rollback_task(
            x, RecoveryRecord("old text restored", EV, "Ali (staff)")
        ),
    }


@pytest.mark.parametrize("frm", [s.value for s in ALL])
def test_only_legal_moves_succeed(frm):
    sc = scope()
    base = task(sc)
    for to, fn in _drivers(sc, base).items():
        t = dataclasses.replace(base, state=TaskState(frm))
        assert fn(t).ok == ((frm, to) in LEGAL), (frm, to)


def test_done_needs_verification_record():
    _, t = running()
    t = mark_performed(t, "x").task
    for bad in (
        None,
        "done",
        {"passed": True},
        verification(passed=False),
        verification(evidence=()),
        verification(acceptance_statement=""),
        verification(acceptance_id=""),
        verification(verifier="pi"),
        verification(verifier="ali (staff)"),
    ):
        r = complete_task(t, bad)
        assert not r.ok and r.task is t
    for kind in ("model_statement", "chat_claim", ""):
        assert not complete_task(
            t, verification(evidence=(Evidence("x", kind, "Omar (staff)"),))
        ).ok
    assert not complete_task(t, verification(evidence=(Evidence("x", "file", "assistant"),))).ok
    assert not complete_task(t, verification(evidence=(Evidence("", "file", "Omar (staff)"),))).ok
    assert not complete_task(t, verification(evidence=["x"])).ok


def test_cannot_skip_to_done_from_running_or_approved():
    sc, t = approved()
    assert not complete_task(t, verification()).ok
    sc, t = running()
    assert not complete_task(t, verification()).ok


def test_rollback_needs_recovery_record_with_evidence():
    _, t = running()
    t = fail_task(t, "broke").task
    for bad in (
        None,
        "restored",
        RecoveryRecord("", EV, "Ali"),
        RecoveryRecord("ok", (), "Ali"),
        RecoveryRecord("ok", EV, "pi"),
    ):
        assert not rollback_task(t, bad).ok
    r = rollback_task(t, RecoveryRecord("old text restored", EV, "Ali (staff)"))
    assert (
        r.ok
        and r.task.state is TaskState.ROLLED_BACK
        and r.task.recovery.restored_state == "old text restored"
    )
    assert not fail_task(r.task, "again").ok


def test_approval_needs_rollback_plan():
    sc = scope()
    base = task(sc)
    for plan in (
        None,
        RollbackPlan((), True, "Ali", "c"),
        RollbackPlan(("s",), False, "Ali", "c"),
        RollbackPlan(("s",), True, "pi", "c"),
        RollbackPlan(("s",), True, "Ali", ""),
        "restore",
    ):
        t = dataclasses.replace(base, rollback=plan)
        assert not approve_task(t, sc, NOW).ok


def test_approval_guards_each_alone():
    sc = scope()
    t = task(sc)
    assert not approve_task(
        t, scope(expires_at=NOW + timedelta(seconds=1)), NOW + timedelta(seconds=2)
    ).ok
    other = scope(
        scope_text=TEXT + " more",
        referenced_sha=scope_sha(TEXT + " more", frozenset(TOOLS), LIMITS),
    )
    assert not approve_task(t, other, NOW).ok  # task was written for a different scope
    assert not approve_task(t, None, NOW).ok
    assert not approve_task(t, sc, datetime(2026, 11, 1)).ok
    assert not approve_task(
        dataclasses.replace(t, owner="Sara (owner)"), sc, NOW
    ).ok  # approver is owner
    assert not approve_task(dataclasses.replace(t, creator="sara (owner)"), sc, NOW).ok
    tampered = scope()
    object.__setattr__(tampered, "scope_text", "do anything")
    assert not approve_task(t, tampered, NOW).ok


def test_start_needs_dependencies_done():
    sc = scope()
    t = approve_task(task(sc, depends_on=["t0"]), sc, NOW).task
    assert not start_task(t, sc, NOW).ok
    assert not start_task(t, sc, NOW, {"t0": "running"}).ok
    assert not start_task(t, sc, NOW, {}).ok
    assert not start_task(t, sc, NOW, "done").ok
    assert start_task(t, sc, NOW, {"t0": "done"}).ok
    assert start_task(t, sc, NOW, {"t0": TaskState.DONE}).ok


def test_new_task_malformed():
    sc = scope()
    for over in (
        dict(id=""),
        dict(id=None),
        dict(owner="pi"),
        dict(owner=""),
        dict(creator=5),
        dict(title=" "),
        dict(scope_sha="abc"),
        dict(depends_on="t0"),
        dict(depends_on=["t1"]),
        dict(depends_on=[None]),
        dict(depends_on=[f"d{i}" for i in range(51)]),
        dict(rollback="x"),
    ):
        args = dict(id="t1", title="T", owner="Ali", creator="Zed", scope_sha=sc.scope_sha)
        args.update(over)
        assert not new_task(**args).ok, over


# ---- DAG ----


def test_dag():
    assert validate_dag({"a": [], "b": ["a"], "c": ["a", "b"]}) == ()
    assert validate_dag({"a": ["b"], "b": ["a"]})
    assert validate_dag({"a": ["b"], "b": ["c"], "c": ["a"]})
    assert validate_dag({"a": ["a"]})
    assert validate_dag({"a": ["ghost"]})
    for bad in (None, [], {"a": "b"}, {"": []}, {"a": [1]}, {1: []}):
        assert validate_dag(bad)
    assert validate_dag({str(i): [] for i in range(5001)})


def test_dag_diamond_is_not_a_cycle():
    assert validate_dag({"a": [], "b": ["a"], "c": ["a"], "d": ["b", "c"]}) == ()


@pytest.mark.parametrize("n", [1_000, 10_000, 100_000])
def test_dag_scaling_is_bounded(n):
    t0 = time.perf_counter()
    r = validate_dag({str(i): [str(i - 1)] if i else [] for i in range(n)})
    assert time.perf_counter() - t0 < 2.0
    assert (r == ()) if n <= 5000 else bool(r)


def test_dag_long_chain_5000_valid_and_cycle_detected():
    chain = {str(i): [str(i - 1)] if i else [] for i in range(5000)}
    assert validate_dag(chain) == ()
    chain["0"] = ["4999"]
    assert validate_dag(chain)


# ---- gate ----


def act(tool="write_note", **kw):
    return ActionRequest(tool, kw.pop("params", {"note": "hello"}), kw.pop("units", 1))


def test_gate_ok_and_each_guard_alone():
    sc, t = approved()
    assert check_can_execute(t, sc, NOW).allowed
    assert check_can_execute(t, sc, NOW, action=act()).allowed
    sc2, t2 = running()
    assert check_can_execute(t2, sc2, NOW, action=act()).allowed

    def deny(d, code=None):
        assert not d.allowed and d.reasons
        if code:
            assert d.code == code

    deny(check_can_execute(t, sc, NOW + timedelta(days=3)))  # expired
    deny(check_can_execute(t, sc, datetime(2026, 11, 1)))  # naive now
    deny(check_can_execute(dataclasses.replace(t, state=TaskState.PROPOSED), sc, NOW), "state")
    deny(check_can_execute(dataclasses.replace(t, state=TaskState.DONE), sc, NOW), "state")
    deny(check_can_execute(dataclasses.replace(t, rollback=None), sc, NOW))
    deny(check_can_execute(dataclasses.replace(t, scope_sha="1" * 64), sc, NOW))  # changed scope
    deny(
        check_can_execute(dataclasses.replace(t, depends_on=("x",)), sc, NOW)
    )  # unknown dep states
    deny(check_can_execute(t, sc, NOW, action=act("read_document")), "outside_scope")
    deny(check_can_execute(t, sc, NOW, action=act("nonexistent")), "unknown_tool")
    deny(
        check_can_execute(t, sc, NOW, action=act("take_payment")),
        "unknown_tool" if False else "forbidden_tool",
    )
    deny(check_can_execute(t, sc, NOW, action=act("request_otp")), "forbidden_tool")


def test_gate_fail_closed_never_raises():
    sc, t = approved()
    junk = [None, 0, "x", object(), [], {}, float("nan")]
    for a in junk:
        for b in junk:
            for c in junk:
                d = check_can_execute(a, b, c)
                assert d.allowed is False
    for a in junk[1:]:
        assert not check_can_execute(t, sc, NOW, action=a).allowed
        assert check_can_execute(t, sc, NOW, used=a, action=act()).allowed == (a == {})
    assert not check_can_execute(t, sc, NOW, action=ActionRequest("write_note", "notadict")).allowed
    assert not check_can_execute(t, sc, NOW, action=ActionRequest("write_note", {}, 0)).allowed
    assert not check_can_execute(t, sc, NOW, action=ActionRequest("write_note", {}, True)).allowed
    assert not check_can_execute(
        t, sc, NOW, action=ActionRequest("write_note", {"a": object()})
    ).allowed


def test_limits():
    sc, t = approved()
    a = act()
    assert check_can_execute(t, sc, NOW, action=a, used={"actions": 2}).allowed
    assert not check_can_execute(t, sc, NOW, action=a, used={"actions": 3}).allowed
    assert not check_can_execute(t, sc, NOW, action=act(units=6)).allowed
    assert not check_can_execute(t, sc, NOW, action=a, used={"actions": -1}).allowed
    assert not check_can_execute(t, sc, NOW, action=a, used={"actions": "0"}).allowed
    assert not check_can_execute(t, sc, NOW, action=a, used={"units": 5}).allowed
    nolimit = scope(
        limits={"max_units": 5}, referenced_sha=scope_sha(TEXT, frozenset(TOOLS), {"max_units": 5})
    )
    t2 = approve_task(task(nolimit), nolimit, NOW).task
    assert not check_can_execute(t2, nolimit, NOW, action=a).allowed  # no max_actions


@pytest.mark.parametrize(
    "tool,params",
    [("send_message", {"to": "customer", "text": "hi"}), ("publish_live", {"site": "staging"})],
)
def test_dangerous_actions_need_separate_explicit_approval(tool, params):
    sc, t = approved()
    a = ActionRequest(tool, params)
    d = check_can_execute(t, sc, NOW, action=a)
    assert not d.allowed and d.code == "needs_approval"

    def ap(**over):
        args = dict(
            action_sha=action_sha(a),
            approver="Sara (owner)",
            approval_text="I approve this action",
            approved_at=NOW - timedelta(minutes=1),
        )
        args.update(over)
        return ActionApproval(**args)

    assert check_can_execute(t, sc, NOW, action=a, action_approval=ap()).allowed
    for bad in (
        ap(approval_text="ok"),
        ap(approval_text="don't proceed"),
        ap(approval_text='"I approve"'),
        ap(action_sha="0" * 64),
        ap(approver="pi"),
        ap(approver="ali (staff)"),
        ap(approved_at=NOW - timedelta(minutes=16)),
        ap(approved_at=NOW + timedelta(minutes=1)),
        ap(approved_at=datetime(2026, 11, 1)),
        "yes",
        None,
    ):
        assert not check_can_execute(t, sc, NOW, action=a, action_approval=bad).allowed
    # approval for one action does not cover a changed action
    changed = ActionRequest(tool, {**params, "extra": 1})
    assert not check_can_execute(t, sc, NOW, action=changed, action_approval=ap()).allowed
    assert not check_can_execute(
        t, sc, NOW, action=ActionRequest(tool, params, 2), action_approval=ap()
    ).allowed


def test_scope_approval_does_not_replace_action_approval():
    # scope approved by owner with explicit yes still never lets a message out without its own approval
    sc, t = approved()
    assert "send_message" in sc.tools
    assert not check_can_execute(
        t, sc, NOW, action=ActionRequest("send_message", {"text": "x"})
    ).allowed


@pytest.mark.parametrize(
    "params",
    [
        {"card_number": "x"},
        {"cvv": 1},
        {"password": "x"},
        {"otp": "123456"},
        {"note": "4111 1111 1111 1111"},
        {"note": "4111-1111-1111-1111"},
        {"nested": {"deep": {"iban": "x"}}},
        {"list": [{"token": "x"}]},
        {"a": {"b": {"c": {"d": {"e": {"f": 1}}}}}},
        {f"k{i}": i for i in range(600)},
        {"big": "x" * 10_001},
    ],
)
def test_no_payment_card_or_password_data_in_actions(params):
    sc, t = approved()
    d = check_can_execute(t, sc, NOW, action=ActionRequest("write_note", params))
    assert not d.allowed and d.code == "bad_params"


# ---- audit ----


def build_log(n=5):
    log = au.AuditLog()
    for i in range(n):
        assert log.append(
            at=NOW + timedelta(seconds=i),
            kind="action",
            actor="Ali",
            task_id="t1",
            detail=f"step {i}",
        )
    return log


def test_chain_ok_and_all_kinds():
    log = au.AuditLog()
    for k in sorted(au.KINDS):
        assert log.append(at=NOW, kind=k, actor="a", task_id="t")
    assert au.verify_chain(log.entries, log.head).ok
    assert au.verify_chain([]).ok


def test_chain_tamper_detection():
    log = build_log()
    es = list(log.entries)
    head = log.head
    # edit content
    bad = es.copy()
    bad[2] = dataclasses.replace(bad[2], detail="nothing happened")
    assert not au.verify_chain(bad).ok and au.verify_chain(bad).bad_index == 2
    # edit and re-hash that entry only: next link breaks
    forged = dataclasses.replace(es[2], detail="forged")
    forged = dataclasses.replace(
        forged,
        hash=au._digest(
            forged.seq,
            forged.at,
            forged.kind,
            forged.actor,
            forged.task_id,
            forged.detail,
            forged.prev_hash,
        ),
    )
    bad = es.copy()
    bad[2] = forged
    assert au.verify_chain(bad).bad_index == 3
    # remove from the middle, reorder, duplicate, insert
    assert not au.verify_chain(es[:2] + es[3:]).ok
    assert not au.verify_chain([es[1], es[0], *es[2:]]).ok
    assert not au.verify_chain([*es[:3], es[2], *es[3:]]).ok
    # change kind to hide a refusal
    r = au.AuditLog()
    r.append(at=NOW, kind="refusal", actor="a", task_id="t")
    assert not au.verify_chain([dataclasses.replace(r.entries[0], kind="action")]).ok
    # drop the tail: needs the anchor
    assert au.verify_chain(es[:-1]).ok
    assert not au.verify_chain(es[:-1], head).ok
    # junk
    for junk in (None, 5, [1, 2], [None], ["x"]):
        assert not au.verify_chain(junk).ok


def test_log_is_append_only_and_bounded():
    log = build_log(2)
    assert not hasattr(log, "update") and not hasattr(log, "delete") and not hasattr(log, "remove")
    assert isinstance(log.entries, tuple)
    assert log.append(at=NOW, kind="bogus", actor="a", task_id="t") is None
    assert log.append(at=datetime(2026, 1, 1), kind="action", actor="a", task_id="t") is None
    assert len(log.entries) == 2
    e = log.append(
        at=NOW,
        kind="action",
        actor="a",
        task_id="t",
        detail="card 4111 1111 1111 1111 mail a@b.com " + "x" * 5000,
    )
    assert "4111" not in e.detail and "a@b.com" not in e.detail and len(e.detail) <= au.MAX_DETAIL


def test_gate_answers_are_recorded():
    sc, t = approved()
    log = au.AuditLog()
    ok = check_can_execute(t, sc, NOW)
    no = check_can_execute(t, sc, NOW + timedelta(days=9))
    assert record_decision(log, t, ok, NOW, "gate").kind == "decision"
    assert record_decision(log, t, no, NOW, "gate").kind == "refusal"
    assert au.verify_chain(log.entries, log.head).ok


@pytest.mark.parametrize("n", [1_000, 10_000, 100_000])
def test_chain_scaling(n):
    log = au.AuditLog()
    t0 = time.perf_counter()
    for i in range(n):
        log.append(at=NOW, kind="action", actor="a", task_id="t", detail=str(i))
    assert au.verify_chain(log.entries, log.head).ok
    assert time.perf_counter() - t0 < 15.0
    assert (log.append(at=NOW, kind="action", actor="a", task_id="t") is None) == (
        n >= au.MAX_ENTRIES
    )


def test_scope_type_is_approved_scope():
    assert isinstance(scope(), ApprovedScope)
