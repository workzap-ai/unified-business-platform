"""The learning-brain gap closers on a real database (spec 8.2, 8.5, 8.6, 8.9, 11.7)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, workspace
from test_pi_learning_loop import model

from app.modules.pi import (
    learning_arms,
    learning_audit,
    learning_bank,
    learning_canary,
    learning_drift,
    learning_gate,
    learning_lessons,
    learning_review,
    learning_seed,
)
from app.modules.pi.learning_models import (
    PiLearningChange,
    PiLearningExample,
    PiQuestionArm,
)
from app.shared.errors import BusinessRuleViolation

pytestmark = pytest.mark.integration

DENTAL, DAIRY = "dental_clinics", "cattle_and_buffalo_dairy_farms"


def example(scope, person, reply, industry="", status="active", contact="x", sector=""):
    sit = {"state": "S2_CLARIFYING", "language": "en", "turn_kind": "question"}
    if industry:
        sit["industry"] = industry
    if sector:
        sit["sector"] = sector
    return PiLearningExample(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        message_id=None,
        situation=sit,
        language="en",
        person_text=person,
        reply_text=reply,
        reward=4,
        status=status,
        source_contacts=[contact],
        redaction_confidence=Decimal("1.0"),
    )


async def test_a_dental_example_is_never_shown_to_a_dairy_farmer(api, business_db, monkeypatch):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    business_db.add_all(
        [
            example(
                scope, "patients miss appointments", "How often do they miss?", DENTAL, contact="a"
            ),
            example(scope, "milk cheques come late", "Which buyer pays last?", DAIRY, contact="b"),
            example(scope, "things are messy", "Where does it show up most?", "", contact="c"),
        ]
    )
    await business_db.flush()
    args = dict(state="S2_CLARIFYING", language="en", said="stock is a mess", k=5)
    farm = await learning_bank.retrieve(business_db, scope, industry=DAIRY, **args)
    assert {e.reply_text for e in farm} == {"Which buyer pays last?", "Where does it show up most?"}
    dentist = await learning_bank.retrieve(business_db, scope, industry=DENTAL, **args)
    assert "Which buyer pays last?" not in {e.reply_text for e in dentist}
    unknown = await learning_bank.retrieve(business_db, scope, **args)  # no industry known
    assert [e.reply_text for e in unknown] == ["Where does it show up most?"]  # only general ones
    await pi.close()


async def test_seeds_are_candidates_scoped_to_an_industry_and_never_active(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    counts = await learning_seed.seed_examples(business_db, scope, {DENTAL, DAIRY})
    assert counts["added"] > 0
    rows = list(await business_db.scalars(select(PiLearningExample)))
    assert rows and {r.status for r in rows} == {"candidate"}  # through the gate, never straight in
    assert {r.source for r in rows} <= {"pack", "golden"} and all(
        r.message_id is None for r in rows
    )
    assert {r.situation.get("industry", "") for r in rows} <= {DENTAL, DAIRY, ""}
    again = await learning_seed.seed_examples(business_db, scope, {DENTAL, DAIRY})
    assert again["added"] == 0  # idempotent
    arms = await learning_seed.seed_arms(business_db, scope, {DENTAL})
    assert arms["added"] > 0
    made = list(
        await business_db.scalars(select(PiQuestionArm).where(PiQuestionArm.industry != ""))
    )
    assert {a.industry for a in made} == {DENTAL}
    assert {a.status for a in made} == {"testing"} and {a.traffic_cap for a in made} == {0.1}
    await pi.close()


async def test_an_industry_wording_is_chosen_only_for_its_industry(api, business_db, monkeypatch):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    await learning_arms.ensure_seeded(business_db, scope)
    arm = PiQuestionArm(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        slot="scope",
        language="en",
        text="Which chair loses the most appointments?",
        status="active",
        industry=DENTAL,
    )
    arm.alpha, arm.beta = 500.0, 1.0  # would always win if it were allowed
    business_db.add(arm)
    await business_db.flush()
    for _ in range(20):
        picked = await learning_arms.choose(business_db, scope, "scope", "en", industry=DAIRY)
        assert picked is not None and picked.industry == ""
    assert (
        await learning_arms.choose(business_db, scope, "scope", "en", industry=DENTAL)
    ).text == arm.text
    await pi.close()


async def test_the_old_shop_seeds_are_retired_and_the_new_ones_say_nothing_about_shops(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    old = PiQuestionArm(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        slot="scope",
        language="en",
        text="Is it every shop, or only some?",
        status="active",
        created_by="seed",
    )
    business_db.add(old)
    await business_db.flush()
    await learning_arms.ensure_seeded(business_db, scope)
    assert old.status == "retired"
    live = await business_db.scalars(select(PiQuestionArm).where(PiQuestionArm.status != "retired"))
    assert not [a.text for a in live if "shop" in a.text.lower() or "dukan" in a.text.lower()]
    await pi.close()


async def test_a_failing_gate_holds_new_canaries_and_new_lessons(api, business_db, monkeypatch):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    assert await learning_gate.allows(business_db, scope)  # nothing recorded: not held
    ripe = example(scope, "stock runs out", "Is it every shop?", status="candidate")
    ripe.created_at = datetime.now(UTC) - timedelta(days=3)
    business_db.add(ripe)
    await business_db.flush()
    await learning_gate.record(
        business_db, scope, learning_gate.GateResult(False, ["1 conversation(s) broke a rule"])
    )
    assert not await learning_gate.allows(business_db, scope)
    held = await learning_bank.activate(business_db, scope, datetime.now(UTC))
    assert held["activated"] == 0 and held["held_by_gate"] == 1 and ripe.status == "candidate"
    lesson = await learning_lessons.propose(
        business_db, scope, "When stock is mentioned, ask which route first", {}, None
    )
    assert lesson.status == "review"  # held for a person while the gate fails
    await learning_gate.record(business_db, scope, learning_gate.GateResult(True))
    assert await learning_gate.allows(business_db, scope)
    went = await learning_bank.activate(business_db, scope, datetime.now(UTC))
    assert went["activated"] == 1 and ripe.status == "canary"
    await pi.close()


async def test_a_low_risk_lesson_goes_through_the_canary_and_rolls_back_automatically(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    now = datetime.now(UTC)
    good = await learning_lessons.propose(
        business_db, scope, "When stock is mentioned, ask which route first", {}, None, "pi"
    )
    bad = await learning_lessons.propose(
        business_db,
        scope,
        "Keep your sentences short when someone is describing a delay",
        {},
        None,
        "pi",
    )
    assert good.status == bad.status == "canary" and good.canary_since is not None
    # Canary lessons reach only the canary share of conversations.
    assert await learning_lessons.relevant(business_db, scope, "S2_CLARIFYING", "en") == []
    shown = await learning_lessons.relevant(
        business_db,
        scope,
        "S2_CLARIFYING",
        "en",
        conversation_id="c-1",
        canary_percent=100,
    )
    assert {x.id for x in shown} == {good.id, bad.id}

    def judge(example_id, *a, **k):
        if example_id == str(bad.id):
            return "rollback", {"breached": ["confusion"], "canary_replies": 9}
        return "promote", {"canary_replies": 400}

    monkeypatch.setattr(learning_canary, "judge", judge)
    result = await learning_canary.evaluate_lessons(
        business_db, scope, now + timedelta(days=5), min_days=2, min_uses=30
    )
    assert result["promoted"] == 1 and result["rolled_back"] == 1
    assert good.status == "live" and bad.status == "retired"
    kinds = {c.kind for c in await business_db.scalars(select(PiLearningChange))}
    assert {"lesson_canary_promoted", "lesson_canary_rolled_back"} <= kinds
    await pi.close()


async def test_a_promotion_waits_while_the_gate_is_failing(api, business_db, monkeypatch):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    lesson = await learning_lessons.propose(
        business_db, scope, "When stock is mentioned, ask which route first", {}, None, "pi"
    )
    monkeypatch.setattr(learning_canary, "judge", lambda *a, **k: ("promote", {}))
    await learning_gate.record(business_db, scope, learning_gate.GateResult(False, ["mean 1.2"]))
    result = await learning_canary.evaluate_lessons(
        business_db, scope, datetime.now(UTC) + timedelta(days=9), min_days=2, min_uses=30
    )
    assert result["promoted"] == 0 and lesson.status == "canary"
    await pi.close()


async def test_a_change_rolled_back_twice_waits_for_a_human_and_is_not_proposed_again(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    text = "When stock is mentioned, ask which route first"
    for _ in range(2):
        business_db.add(
            PiLearningChange(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                kind="lesson_canary_rolled_back",
                status="rolled_back",
                evidence={"signature": learning_canary.signature(text)},
                reason="guardrail rose: confusion",
            )
        )
    await business_db.flush()
    [item] = await learning_review.rolled_back_twice(business_db, scope)
    assert item["times"] == 2 and item["kind"] == "lesson"
    with pytest.raises(BusinessRuleViolation):
        await learning_lessons.propose(business_db, scope, text, {}, None, "pi")
    queue = await api.get("/api/v1/pi/brain-learning/queue")
    assert queue.json()["rolled_back_twice"][0]["signature"] == item["signature"]
    done = await learning_review.decide(business_db, scope, item["change_ids"], None)
    assert done == 2 and await learning_review.rolled_back_twice(business_db, scope) == []
    await pi.close()


async def test_a_rejected_lesson_is_not_proposed_again_by_the_miner(api, business_db, monkeypatch):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    text = "When delivery is late, ask which route it was on first"
    lesson = await learning_lessons.propose(business_db, scope, text, {}, None, "pi")
    lesson.status = "review"
    await learning_lessons.decide(business_db, scope, lesson, False, None, "too narrow")
    assert lesson.status == "rejected"
    with pytest.raises(BusinessRuleViolation):
        await learning_lessons.propose(business_db, scope, text.upper(), {}, None, "pi")
    assert await learning_lessons.rejected_reasons(business_db, scope) == ["too narrow"]
    again = await learning_lessons.propose(business_db, scope, text, {}, None, "staff")
    assert again.status == "canary"  # a person may still teach it
    arm, _ = await learning_arms.propose(
        business_db, scope, "scope", "en", "Which route is late?", "miner"
    )
    assert arm is not None
    arm.status = "retired"
    refused, why = await learning_arms.propose(
        business_db, scope, "scope", "en", "which route is late?", "miner"
    )
    assert refused is None and why
    await pi.close()


async def test_the_frozen_drift_reference_is_stored_once(api, business_db, monkeypatch):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    current = learning_drift.Stats(40, 20.0, 0.0, 0.0, 0.0)
    first = await learning_drift._frozen_reference(business_db, scope, current)
    later = learning_drift.Stats(40, 90.0, 0.0, 0.0, 0.0)
    second = await learning_drift._frozen_reference(business_db, scope, later)
    assert first[1] == current and second[1] == current  # the first real week never moves
    rows = list(
        await business_db.scalars(
            select(PiLearningChange).where(PiLearningChange.kind == learning_drift.REFERENCE_KIND)
        )
    )
    assert len(rows) == 1
    await pi.close()


async def test_every_reply_can_be_traced_to_what_it_used(api, business_db, monkeypatch):
    from test_pi_learning_loop import good_chat, learning_on

    from app.modules.pi.experience_scorer import score_new
    from app.modules.pi.learning_models import PiReplyAudit
    from app.modules.pi.models import PiMessage

    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await learning_on(api)
    await good_chat(pi, business_db)
    scope = pi.scope()
    conversation = await pi.conversation()
    reply = (
        await business_db.scalars(
            select(PiMessage)
            .where(PiMessage.direction == "outbound", PiMessage.sender_type == "ai")
            .order_by(PiMessage.created_at)
        )
    ).first()
    lesson = await learning_lessons.propose(
        business_db, scope, "When stock is mentioned, ask which route first", {}, None, "pi"
    )
    from app.modules.pi.models import PiAgentRun

    run = await business_db.scalar(
        select(PiAgentRun).where(PiAgentRun.response_message_id == reply.id)
    )
    conversation.service_brief = {
        **(conversation.service_brief or {}),
        "learning_used": [
            {
                "message_id": str(run.message_id),
                "arm": None,
                "voice_arm": None,
                "examples": ["e-1"],
                "lessons": [str(lesson.id)],
                "industry": DENTAL,
            }
        ],
    }
    row = await learning_audit.stamp(
        business_db, scope, conversation, reply, violations=[], response_rules={}
    )
    assert row.lesson_ids == [str(lesson.id)] and row.example_ids == ["e-1"]
    assert row.prompt_version == learning_audit.prompt_version()
    assert list(row.pack_versions) == [DENTAL] and row.linter == {"passed": True, "violations": []}
    assert row.frozen is True  # response_rules {} is frozen: the stamp says so
    again = await learning_audit.stamp(business_db, scope, conversation, reply)
    assert again.id == row.id  # one row per reply
    assert (await learning_audit.trace(business_db, reply.id)).id == row.id
    assert await business_db.scalar(select(PiReplyAudit.id)) == row.id
    await score_new(business_db)
    await pi.close()


async def test_the_scored_situation_carries_industry_category_and_person_type(
    api, business_db, monkeypatch
):
    from test_pi_learning_loop import good_chat, learning_on

    from app.modules.pi.experience_models import PiExperience
    from app.modules.pi.experience_scorer import score_new

    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await learning_on(api)
    await good_chat(pi, business_db)
    conversation = await pi.conversation()
    conversation.service_brief = {
        **(conversation.service_brief or {}),
        "customer_profile": {"role": "owner", "team_size": "5 staff"},
    }
    await score_new(business_db)
    rows = list(await business_db.scalars(select(PiExperience)))
    assert rows
    for row in rows:
        assert {"state", "language", "turn_kind"} <= set(row.situation)  # the old key survives
    assert any(r.situation.get("person_type") == "owner_small" for r in rows)
    await pi.close()


async def test_the_replay_gate_reads_stored_conversations_and_blocks_a_rule_break(
    api, business_db, monkeypatch
):
    from test_pi_learning_loop import good_chat

    from app.modules.pi.experience_scorer import score_new
    from app.modules.pi.models import PiMessage

    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await good_chat(pi, business_db)
    await score_new(business_db)
    scope = pi.scope()
    clean = await learning_gate.replay(business_db, scope, 200)
    assert clean.conversations >= 1 and clean.ok, clean.reasons
    first = (
        await business_db.scalars(
            select(PiMessage)
            .where(PiMessage.direction == "outbound", PiMessage.sender_type == "ai")
            .order_by(PiMessage.created_at)
        )
    ).first()
    first.body = "Please send your card number and the OTP so I can check?"
    await business_db.flush()
    broken = await learning_gate.replay(business_db, scope, 200)
    assert not broken.ok and broken.broken
    row = await learning_gate.record(business_db, scope, broken)
    assert row.status == "failed" and not await learning_gate.allows(business_db, scope)
    await pi.close()
