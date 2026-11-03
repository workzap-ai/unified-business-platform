"""Two workspaces, one database: what one workspace's pi learned is never read by the other.

Learned examples, lessons, never-say phrases, question arms and the replay gate's conversations are
all keyed by tenant and environment. Each check has a control (the workspace that owns the data does
see it), so a test that finds nothing cannot pass for the wrong reason."""

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, workspace
from test_pi_learning_gaps_db import example
from test_pi_learning_loop import good_chat, model
from test_pi_pipeline import pi_workspace

from app.modules.pi import (
    learning_arms,
    learning_audit,
    learning_bank,
    learning_gate,
    learning_lessons,
)
from app.modules.pi.experience_scorer import score_new
from app.modules.pi.learning_models import PiLearningLesson, PiQuestionArm, PiReplyAudit

pytestmark = pytest.mark.integration


async def two_workspaces(api, db, monkeypatch):
    adaptive(monkeypatch, model)
    first = await workspace(api, db)
    second = await pi_workspace(api, db, business_type="service_business", number="987654321")
    assert first.tenant_id != second.tenant_id
    return first, second


async def test_examples_of_one_workspace_are_not_retrieved_by_the_other(
    api, business_db, monkeypatch
):
    mine, theirs = await two_workspaces(api, business_db, monkeypatch)
    row = example(mine.scope(), "stock runs out in two shops", "Is it every shop, or only some?")
    business_db.add(row)
    await business_db.flush()
    args = dict(state=row.situation["state"], language="en", said="stock runs out", k=3)
    own = await learning_bank.retrieve(business_db, mine.scope(), **args)
    other = await learning_bank.retrieve(business_db, theirs.scope(), **args)
    assert [e.id for e in own] == [row.id]  # control: the owner sees it
    assert other == []


async def test_lessons_and_never_say_phrases_stay_in_their_workspace(api, business_db, monkeypatch):
    mine, theirs = await two_workspaces(api, business_db, monkeypatch)
    lesson = await learning_lessons.propose(
        business_db,
        mine.scope(),
        "Ask which shop it is before asking how often it happens.",
        None,
        None,
    )
    lesson.status = "live"
    await learning_lessons.add_never_say(business_db, mine.scope(), "leave it with me", None, None)
    await business_db.flush()
    state = "S1_LISTENING"
    own = await learning_lessons.relevant(business_db, mine.scope(), state, "en")
    assert [r.id for r in own] == [lesson.id]  # control
    assert await learning_lessons.never_say(business_db, mine.scope(), state, "en") == [
        "leave it with me"
    ]
    assert await learning_lessons.relevant(business_db, theirs.scope(), state, "en") == []
    assert await learning_lessons.never_say(business_db, theirs.scope(), state, "en") == []
    rows = list(await business_db.scalars(select(PiLearningLesson)))
    assert {r.tenant_id for r in rows} == {mine.scope().tenant_id}


async def test_question_arms_are_seeded_and_read_per_workspace(api, business_db, monkeypatch):
    mine, theirs = await two_workspaces(api, business_db, monkeypatch)
    business_db.add(
        PiQuestionArm(
            tenant_id=mine.scope().tenant_id,
            environment_id=mine.scope().environment_id,
            slot="scope",
            language="en",
            text="Is it every shop, or only some?",
            status="active",
            created_by="staff",
        )
    )
    await business_db.flush()
    await learning_arms.ensure_seeded(business_db, theirs.scope())
    seen = list(
        await business_db.scalars(
            select(PiQuestionArm).where(PiQuestionArm.tenant_id == theirs.scope().tenant_id)
        )
    )
    assert all(a.created_by != "staff" for a in seen)  # their seed, not my staff wording
    assert all(a.tenant_id == theirs.scope().tenant_id for a in seen)


async def test_the_replay_gate_grades_only_its_own_workspaces_chats(api, business_db, monkeypatch):
    mine, theirs = await two_workspaces(api, business_db, monkeypatch)
    await good_chat(mine, business_db)
    await score_new(business_db)
    own = await learning_gate.replay(business_db, mine.scope(), 200)
    other = await learning_gate.replay(business_db, theirs.scope(), 200)
    assert own.conversations >= 1  # control
    assert other.conversations == 0


async def test_a_reply_audit_row_is_traced_only_inside_its_own_workspace(
    api, business_db, monkeypatch
):
    mine, theirs = await two_workspaces(api, business_db, monkeypatch)
    await good_chat(mine, business_db)
    row = await business_db.scalar(select(PiReplyAudit).limit(1))
    assert row is not None
    found = await learning_audit.trace(business_db, mine.scope(), row.message_id)
    assert found is not None and found.id == row.id  # control
    assert await learning_audit.trace(business_db, theirs.scope(), row.message_id) is None
