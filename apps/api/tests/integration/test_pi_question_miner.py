"""The question miner proposes new wordings only where the best is below target (spec 8.5 job 3)."""

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, workspace
from test_pi_learning_loop import model

from app.modules.pi import learning_arms, learning_miner
from app.modules.pi.learning_models import PiQuestionArm

pytestmark = pytest.mark.integration


def writer(texts):
    async def write(slot, language, current):
        write.seen = (slot, language, list(current))
        return texts

    return write


async def test_a_weak_slot_gets_new_candidates_that_start_in_test(api, business_db, monkeypatch):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    await learning_arms.ensure_seeded(business_db, scope)
    arms = list(
        await business_db.scalars(
            select(PiQuestionArm).where(
                PiQuestionArm.slot == "scope", PiQuestionArm.language == "en"
            )
        )
    )
    for arm in arms:  # every English scope wording has been used a lot and works badly
        arm.uses, arm.alpha, arm.beta = 60, 5.0, 25.0
    await business_db.flush()
    good = ["Which of your shops does it hit first?", "Is it one shop or all of them?"]
    bad = ["What is your card number? Which shop?", "Tell me more about it"]
    write = writer([*good, *bad])
    counts = await learning_miner.mine(business_db, scope, write)
    assert counts["proposed"] == 2 and counts["refused"] >= 1
    assert write.seen[0] == "scope" and write.seen[1] == "en"
    new = list(
        await business_db.scalars(select(PiQuestionArm).where(PiQuestionArm.created_by == "miner"))
    )
    assert {a.text for a in new} == set(good[:2]) or len(new) == 2
    assert all(a.status == "testing" and a.traffic_cap == 0.10 for a in new)
    await pi.close()


async def test_a_slot_that_works_or_is_unproven_is_left_alone(api, business_db, monkeypatch):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    write = writer(["Which shop is it?"])
    assert (await learning_miner.mine(business_db, scope, write))["proposed"] == 0  # too few uses
    assert (await learning_miner.mine(business_db, scope, None))["proposed"] == 0  # no writer
    await pi.close()
