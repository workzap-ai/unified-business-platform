# ruff: noqa: E501
"""Level 3 controlled execution: approval grammar, seal, allow-list, screening, acceptance evidence,
rollback, 'done' only with evidence, flag off. Pure, no database."""

import os

os.environ.setdefault("PI_EXECUTION_SEAL_KEY", "unit-test-seal-key-0123456789")

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.pi import execution_flow as ef
from app.modules.pi import execution_screen as screen
from app.modules.pi import execution_task as et
from app.modules.pi import execution_tools as tools
from app.modules.pi.execution_scope import seal_key_configured

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(days=3)
TOOLS = ["create_staff_task", "write_note"]


def proposed(run=None):
    run = run or ef.new_run()
    step = run.propose(
        scope_text="Create a staff task and record a note for the Okara dairy rollout.",
        tools=TOOLS,
        limits={"max_actions": 5, "max_units": 5},
        expires_at=LATER,
        owner="Asad Khan",
        creator="Sana Malik",
        now=NOW,
    )
    assert step.ok, step.reasons
    return run


def approved():
    run = proposed()
    s = run.approve_scope(
        approver="Hina Raza", approval_text="I approve", source="owner_chat", now=NOW
    )
    assert s.ok, s.reasons
    return run


def with_task(run=None, deps=()):
    run = run or approved()
    s = run.add_task(
        id="t1", title="Set up the rollout task", owner="Asad Khan", depends_on=list(deps),
        rollback_steps=["cancel the staff task"], rollback_owner="Sana Malik",
        rollback_check="the task shows cancelled", acceptance_id="a1",
        acceptance_statement="The staff task exists and is assigned", now=NOW,
    )  # fmt: skip
    assert s.ok, s.reasons
    assert run.approve_task("t1", NOW).ok
    assert run.start("t1", NOW, "Asad Khan").ok
    return run


def acted(run=None):
    run = with_task(run)
    s = run.execute_action("t1", "create_staff_task", {"title": "Call the dairy"}, NOW, "Asad Khan")
    assert s.ok, s.reasons
    return run, s.data["effect_id"]


# ---- approval grammar and scope seal ----


@pytest.mark.parametrize(
    "text",
    [
        "ok",
        "hmm",
        "maybe",
        "let me think",
        "sure",
        "yes",
        "theek hai",
        "I approve?",
        "not approved",
    ],
)
def test_weak_or_conditional_replies_never_approve(text):
    run = proposed()
    s = run.approve_scope(approver="Hina Raza", approval_text=text, source="owner_chat", now=NOW)
    assert not s.ok and run.scope is None


def test_approver_must_differ_from_owner_and_creator_and_not_be_a_model():
    for who in ("Asad Khan", "Sana Malik", "pi", "assistant"):
        run = proposed()
        assert not run.approve_scope(
            approver=who, approval_text="I approve", source="owner_chat", now=NOW
        ).ok


def test_scope_is_exact_and_seal_is_checked():
    run = approved()
    assert run.scope.is_intact()
    forged = replace(run.scope, tools=run.scope.tools | {"take_payment"})
    assert not forged.is_intact()
    run.scope = forged
    r = run.add_task(id="t9", title="x", owner="Asad Khan", depends_on=[], rollback_steps=["undo"],
                     rollback_owner="Sana Malik", rollback_check="seen", acceptance_id="a", acceptance_statement="ok seen", now=NOW)  # fmt: skip
    assert r.ok  # task can be proposed ...
    assert not run.approve_task("t9", NOW).ok  # ... but never approved under a forged scope


def test_scope_with_external_or_payment_tool_is_refused():
    for bad in (
        "send_message",
        "send_email",
        "take_payment",
        "publish_live",
        "request_otp",
        "run_code",
    ):
        assert not ef.new_run().propose(scope_text="do it", tools=[bad], limits=None, expires_at=LATER,
                                        owner="Asad Khan", creator="Sana Malik", now=NOW).ok  # fmt: skip


def test_expired_scope_blocks_execution():
    run = with_task()
    s = run.execute_action(
        "t1", "write_note", {"text": "late"}, LATER + timedelta(days=1), "Asad Khan"
    )
    assert not s.ok


# ---- allow-list and screening ----


def test_allow_list_is_exactly_the_five_internal_tools():
    assert set(tools.ALLOW_LIST) == {
        "create_staff_task", "create_draft_document", "schedule_followup", "write_note", "update_problem_status"
    }  # fmt: skip
    assert tools.validate("send_message", {"text": "hi"})
    assert tools.validate("write_note", {"text": "ok note"}) is None


def test_tool_outside_scope_is_refused_even_if_allow_listed():
    run = with_task()
    s = run.execute_action(
        "t1", "schedule_followup", {"note": "ping", "due_in_days": 2}, NOW, "Asad Khan"
    )
    assert not s.ok


def test_problem_status_cannot_claim_resolved():
    assert tools.validate(
        "update_problem_status",
        {"problem_ref": "p1", "status": "resolved", "prior_status": "draft"},
    )


@pytest.mark.parametrize(
    "text",
    [
        "my password is hunter22", "otp 482913", "card 4111 1111 1111 1111", "sk-live-abcdef123456",
        "IBAN PK36SCBL0000001123456702", "CNIC 35202-1234567-1", "api key abc", "Bearer eyJhbGciOiJIUzI1NiJ9.x.y",
        "ghp_abcdefghijklmnop", "pin: 1234", "token=abcd1234efgh5678ijkl", "call 03001234567",
        "AKIAIOSFODNN7EXAMPLE", "0123456789abcdef0123", "پاسورڈ بھیجیں",
    ],
)  # fmt: skip
def test_screening_rejects_secret_shapes_and_keywords(text):
    assert screen.text_issue(text)
    assert tools.validate("write_note", {"text": text})


def test_screening_passes_plain_business_text_and_rejects_secret_field_names():
    assert screen.text_issue("Call the Okara dairy on Tuesday about 3 milk coolers") is None
    assert screen.value_issue({"title": "x", "otp": "1"})
    assert tools.validate("write_note", {"text": "hello", "extra": "x"})  # unknown field


def test_secret_in_task_text_or_scope_is_refused():
    assert not ef.new_run().propose(scope_text="use password hunter2", tools=["write_note"], limits=None,
                                    expires_at=LATER, owner="Asad Khan", creator="Sana Malik", now=NOW).ok  # fmt: skip
    run = approved()
    s = run.add_task(id="t2", title="send otp 123456", owner="Asad Khan", depends_on=[], rollback_steps=["undo"],
                     rollback_owner="Sana Malik", rollback_check="seen", acceptance_id="a", acceptance_statement="seen ok", now=NOW)  # fmt: skip
    assert not s.ok


def test_tool_result_is_screened(monkeypatch):
    bad = tools.Effect(
        "write_note", "staff_observation", "note", {"type": "note", "text": "password hunter2"}, {}
    )
    monkeypatch.setitem(tools._HANDLERS, "write_note", lambda p: bad)
    assert isinstance(tools.run_tool("write_note", {"text": "fine"}), str)


# ---- tasks, dependencies, execution record ----


def test_dependencies_must_be_done_and_cycles_refused():
    run = with_task()
    assert not run.add_task(id="t1b", title="loop", owner="Asad Khan", depends_on=["t1b"], rollback_steps=["u"],
                            rollback_owner="Sana Malik", rollback_check="c", acceptance_id="a", acceptance_statement="s ok", now=NOW).ok  # fmt: skip
    assert run.add_task(id="t2", title="after", owner="Asad Khan", depends_on=["t1"], rollback_steps=["u"],
                        rollback_owner="Sana Malik", rollback_check="c", acceptance_id="a2", acceptance_statement="s ok", now=NOW).ok  # fmt: skip
    assert run.approve_task("t2", NOW).ok
    assert not run.start("t2", NOW, "Asad Khan").ok  # t1 not done


def test_action_needs_running_task_and_respects_limit():
    run = approved()
    run.add_task(id="t1", title="x", owner="Asad Khan", depends_on=[], rollback_steps=["u"], rollback_owner="Sana Malik",
                 rollback_check="c", acceptance_id="a", acceptance_statement="s ok", now=NOW)  # fmt: skip
    assert not run.execute_action(
        "t1", "write_note", {"text": "n"}, NOW, "Asad Khan"
    ).ok  # still proposed
    run.approve_task("t1", NOW)
    run.start("t1", NOW, "Asad Khan")
    for i in range(5):
        assert run.execute_action("t1", "write_note", {"text": f"note {i}"}, NOW, "Asad Khan").ok
    assert not run.execute_action("t1", "write_note", {"text": "six"}, NOW, "Asad Khan").ok


def test_every_action_has_an_execution_record_and_audit_entry():
    run, eid = acted()
    assert run.effects[0]["id"] == eid and run.effects[0]["task_id"] == "t1"
    kinds = [e.kind for e in run.log.entries]
    assert "action" in kinds and "decision" in kinds


# ---- acceptance evidence, done, rollback ----


def test_done_needs_independent_verifier_and_real_evidence():
    run, eid = acted()
    assert run.finish_work("t1", NOW, "Asad Khan").ok
    assert run.tasks["t1"].state is et.TaskState.VERIFYING
    assert run.outcome()["implementation_status"] != "implemented"
    assert not run.verify(
        "t1", verifier="Asad Khan", passed=True, evidence_refs=[eid], now=NOW
    ).ok  # the owner
    assert not run.verify("t1", verifier="pi", passed=True, evidence_refs=[eid], now=NOW).ok
    assert not run.verify("t1", verifier="Hina Raza", passed=True, evidence_refs=[], now=NOW).ok
    assert not run.verify(
        "t1", verifier="Hina Raza", passed=True, evidence_refs=["I did it"], now=NOW
    ).ok
    assert run.tasks["t1"].state is et.TaskState.VERIFYING
    assert run.verify("t1", verifier="Hina Raza", passed=True, evidence_refs=[eid], now=NOW).ok
    assert run.tasks["t1"].state is et.TaskState.DONE
    assert run.outcome()["implementation_status"] == "implemented"
    assert "done and verified" in ef.report_text(run)


def test_cannot_finish_without_any_recorded_action_and_no_done_without_it():
    run = with_task()
    assert not run.finish_work("t1", NOW, "Asad Khan").ok
    assert run.outcome()["implementation_status"] == "approved"
    assert "done" not in ef.report_text(run).lower().replace("not yet", "")


def test_failed_acceptance_fails_then_rollback_reverses_records():
    run, eid = acted()
    run.finish_work("t1", NOW, "Asad Khan")
    assert run.verify("t1", verifier="Hina Raza", passed=False, evidence_refs=[eid], now=NOW).ok
    assert run.tasks["t1"].state is et.TaskState.FAILED
    assert run.outcome()["implementation_status"] != "implemented"
    assert run.rollback("t1", recorder="Sana Malik", now=NOW).ok
    assert run.tasks["t1"].state is et.TaskState.ROLLED_BACK
    assert run.effects[0]["rolled_back"] and run.tasks["t1"].recovery.evidence
    assert "rollback" in [e.kind for e in run.log.entries]


def test_rollback_only_from_failed():
    run, _ = acted()
    assert not run.rollback("t1", recorder="Sana Malik", now=NOW).ok


def test_task_without_rollback_plan_cannot_be_approved():
    run = approved()
    r = run.add_task(id="t3", title="x", owner="Asad Khan", depends_on=[], rollback_steps=[],
                     rollback_owner="Sana Malik", rollback_check="c", acceptance_id="a", acceptance_statement="s ok", now=NOW)  # fmt: skip
    assert not r.ok


# ---- persistence round trip and tamper detection ----


def test_roundtrip_and_tampering_is_detected():
    run, eid = acted()
    run.finish_work("t1", NOW, "Asad Khan")
    run.verify("t1", verifier="Hina Raza", passed=True, evidence_refs=[eid], now=NOW)
    data = ef.to_json(run)
    back = ef.from_json(__import__("json").loads(__import__("json").dumps(data)))
    assert back.outcome()["implementation_status"] == "implemented"
    # a stored 'done' forged from 'approved' fails the seal
    import copy

    forged = copy.deepcopy(data)
    forged["tasks"]["t1"]["state"] = "approved"
    with pytest.raises(ef.TamperedRun):
        ef.from_json(forged)
    forged = copy.deepcopy(data)
    forged["audit"][0]["detail"] = "edited"
    with pytest.raises(ef.TamperedRun):
        ef.from_json(forged)
    forged = copy.deepcopy(data)
    forged["scope"]["tools"].append("take_payment")
    with pytest.raises(ef.TamperedRun):
        ef.from_json(forged)


# ---- flag and key ----


def test_flag_off_by_default_and_needs_brain_mode():
    assert ef.availability({})[0] is False
    assert ef.availability({"pi_mode": "brain"})[0] is False
    assert ef.availability({"pi_mode": "brain", "brain": {"level3_exec": "true"}})[0] is False
    assert ef.availability({"brain": {"level3_exec": True}})[0] is False
    assert ef.availability({"pi_mode": "brain", "brain": {"level3_exec": True}})[0] is True


def test_inert_in_production_without_seal_key(monkeypatch):
    monkeypatch.delenv("PI_EXECUTION_SEAL_KEY", raising=False)
    on, why = ef.availability({"pi_mode": "brain", "brain": {"level3_exec": True}}, "production")
    assert not on and "PI_EXECUTION_SEAL_KEY" in why and not seal_key_configured()
    monkeypatch.setenv("PI_EXECUTION_SEAL_KEY", "x" * 20)
    assert ef.availability({"pi_mode": "brain", "brain": {"level3_exec": True}}, "production")[0]
