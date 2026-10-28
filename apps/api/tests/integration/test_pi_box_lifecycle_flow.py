"""The Solution Box lifecycle on the database: moves persisted with times, the offer once, the
yes before drafting, staff-only send with a reviewer, the owner's answers, box v2, and the
decline quiet window. Real database; nothing is sent."""

from types import SimpleNamespace

import pytest
from test_pi_pipeline import pi_workspace
from test_pi_staff_review import scoped

from app.modules.pi import box, box_lifecycle
from app.modules.pi.box_models import PiOfferLog
from app.modules.pi.configuration import settings_row
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

pytestmark = pytest.mark.integration

READY = box.OfferFacts(
    problem_count=4,
    understood_count=3,
    map_reviewed=True,
    ranked=True,
    voluntary_count=2,
    pi_message_count=9,
)
ON = {"pi_mode": "brain", "brain": {"box_offer": True}}


async def chat(api, db, *, box_on=True):
    pi = await pi_workspace(api, db)
    await pi.process("My shop stock keeps running out", "bx-1")
    conversation = await pi.conversation()
    scope = WorkspaceScope.system(
        conversation.tenant_id, conversation.environment_id, frozenset(), "test"
    )
    if box_on:  # the document hooks read the workspace's own setting
        settings = await settings_row(db, scope)
        settings.response_rules = {**(settings.response_rules or {}), **ON}
        await db.flush()
    return conversation, scope


def decision(brief=None, effects=None):
    return SimpleNamespace(brief=brief or {}, effects=effects or [])


async def test_the_whole_lifecycle_is_persisted_in_order(api, business_db):
    conversation, scope = await chat(api, business_db)
    customer = conversation.customer_id
    made, rule = await box_lifecycle.offer(business_db, scope, customer, conversation.id, READY)
    assert (made, rule) == (True, "B")
    row = await box_lifecycle.latest_box(business_db, scope, customer)
    assert row.state == "offered" and row.offered_at is not None
    # once only
    again, why = await box_lifecycle.offer(business_db, scope, customer, conversation.id, READY)
    assert again is False and why == "already offered"
    # an "ok" is not a yes
    with pytest.raises(BusinessRuleViolation):
        await box_lifecycle.move(business_db, scope, row, "drafting", "pi")
    brief: dict = {}
    await box_lifecycle.on_decision(
        business_db, scope, conversation, decision(effects=["request_solution"]), brief, ON
    )
    assert row.state == "drafting"
    await box_lifecycle.on_draft_ready(business_db, scope, customer)
    assert row.state == "in_review"
    with pytest.raises(BusinessRuleViolation):  # pi and the owner never send; no reviewer yet
        await box_lifecycle.move(business_db, scope, row, "sent", "pi")
    with pytest.raises(BusinessRuleViolation):
        await box_lifecycle.move(business_db, scope, row, "sent", "staff", approved_document=True)
    await box_lifecycle.move(
        business_db, scope, row, "sent", "staff", actor_ref="Sara", approved_document=True
    )
    assert row.reviewer == "Sara"
    await box_lifecycle.move(business_db, scope, row, "accepted", "owner")
    log = await box_lifecycle.transitions_of(business_db, scope, row.id)
    assert [(t.from_state, t.to_state, t.actor) for t in log] == [
        ("collecting", "ready", "pi"),
        ("ready", "offered", "pi"),
        ("offered", "drafting", "pi"),
        ("drafting", "in_review", "pi"),
        ("in_review", "sent", "staff"),
        ("sent", "accepted", "owner"),
    ]
    assert all(t.created_at is not None for t in log)
    fresh = await box_lifecycle.new_version(business_db, scope, row, reason="new problem")
    assert (fresh.version, fresh.state, fresh.parent_box_id) == (2, "collecting", row.id)
    assert row.state == "revised"


async def test_a_blocked_offer_is_logged_and_changes_nothing(api, business_db):
    conversation, scope = await chat(api, business_db)
    thin = box.OfferFacts(problem_count=1)
    made, why = await box_lifecycle.offer(
        business_db, scope, conversation.customer_id, conversation.id, thin
    )
    assert made is False and why.startswith("B: B1")
    assert await box_lifecycle.latest_box(business_db, scope, conversation.customer_id) is None
    logged = (
        await business_db.scalars(
            PiOfferLog.__table__.select().where(PiOfferLog.conversation_id == conversation.id)
        )
    ).all()
    assert len(logged) == 1


async def test_the_decision_hooks_follow_the_gates_and_a_decline_returns_to_collecting(
    api, business_db
):
    conversation, scope = await chat(api, business_db)
    brief: dict = {}
    await box_lifecycle.on_decision(
        business_db, scope, conversation, decision({"offer_asked": True}), brief, ON
    )
    row = await box_lifecycle.latest_box(business_db, scope, conversation.customer_id)
    assert row.state == "offered"
    await box_lifecycle.on_decision(
        business_db, scope, conversation, decision({"offer_declined": True}), brief, ON
    )
    assert row.state == "collecting"
    assert brief["box_declined_at"] and isinstance(brief[box_lifecycle.DECLINE_KEY], int)
    assert box_lifecycle.quiet_after_decline(brief, brief[box_lifecycle.DECLINE_KEY] + 3)


async def test_with_the_flag_off_nothing_is_written(api, business_db):
    conversation, scope = await chat(api, business_db, box_on=False)
    brief: dict = {}
    await box_lifecycle.on_decision(
        business_db, scope, conversation, decision({"offer_asked": True}), brief, {}
    )
    await box_lifecycle.on_decision(
        business_db, scope, conversation, decision({"offer_asked": True}), brief,
        {"pi_mode": "brain"},
    )  # fmt: skip
    await box_lifecycle.on_draft_ready(business_db, scope, conversation.customer_id)
    assert await box_lifecycle.latest_box(business_db, scope, conversation.customer_id) is None
    assert scoped(conversation)
