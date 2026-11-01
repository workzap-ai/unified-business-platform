"""E2c on the real database: two workspaces, one database. A chat's category and industry, and the
summary message the board is built for, are read inside the asking workspace when it is named.

Each check has a control (the workspace that owns the data does see it), so a test that finds
nothing cannot pass for the wrong reason."""

import pytest
from sqlalchemy import func, select
from test_pi_brain_flow import brain_on
from test_pi_brain_problems import create, problems_of, say, workspace
from test_pi_industry_context import scripted
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import turn

from app.modules.pi import brain_visual_queue, learning_situation
from app.modules.pi.models import PiMessage

pytestmark = pytest.mark.integration


async def two_noted_workspaces(api, db, monkeypatch):
    scripted(
        monkeypatch,
        turn(
            reply="Hi, I'm pi, an AI from Workzap. Thanks. I've noted it. Anything else?",
            language="en",
            problem_ops=[create("Best-sellers run out", "We keep running out of best-sellers.")],
        ),
    )
    mine = await workspace(api, db)
    theirs = await pi_workspace(api, db, business_type="service_business", number="987654321")
    assert mine.tenant_id != theirs.tenant_id
    await brain_on(api)  # the signed-in workspace is now the second one
    await say(mine, "Our best-sellers keep running out", "e2c-a")
    await say(theirs, "Our best-sellers keep running out", "e2c-b")
    # both workspaces really have a noted problem, or a search that finds nothing proves nothing
    for pi in (mine, theirs):
        _, noted = await problems_of(db, pi)
        assert len(noted) == 1
    return mine, theirs


async def test_category_and_industry_are_read_inside_the_named_workspace(
    api, business_db, monkeypatch
):
    mine, theirs = await two_noted_workspaces(api, business_db, monkeypatch)
    conversation, [problem] = await problems_of(business_db, mine)
    customer_id = conversation.customer_id
    from app.modules.customers.models import Customer

    customer = await business_db.get(Customer, customer_id)
    customer.industry_primary = "retail_and_wholesale"
    await business_db.flush()

    own = await learning_situation.category_of(business_db, conversation.id, scope=mine.scope())
    other = await learning_situation.category_of(business_db, conversation.id, scope=theirs.scope())
    assert own == problem.category == "stock_inventory"  # control: the owner reads it
    assert other == ""
    own_industry = await learning_situation.industry_of(
        business_db, conversation, scope=mine.scope()
    )
    other_industry = await learning_situation.industry_of(
        business_db, conversation, scope=theirs.scope()
    )
    assert own_industry == "retail_and_wholesale"  # control
    assert other_industry == ""
    # no scope: behaviour as before, the caller's own reachability is what protects it
    assert await learning_situation.category_of(business_db, conversation.id) == "stock_inventory"


async def test_a_summary_message_of_another_workspace_is_not_attached_to(
    api, business_db, monkeypatch, settings
):
    mine, theirs = await two_noted_workspaces(api, business_db, monkeypatch)
    mine_conversation = await mine.conversation()
    theirs_conversation = await theirs.conversation()
    summary = await brain_visual_queue._queue_reply(
        business_db, mine.scope(), mine_conversation, "Your problems so far.", "e2c-summary", {}
    )

    async def board_messages(tenant_id):
        return await business_db.scalar(
            select(func.count())
            .select_from(PiMessage)
            .where(PiMessage.tenant_id == tenant_id, PiMessage.idempotency_key.like("pi-board:%"))
        )

    # the other workspace names a message that is not theirs: nothing is found, nothing is added
    got = await brain_visual_queue.attach_board(
        business_db, theirs.scope(), settings, theirs_conversation, [summary], "en"
    )
    assert got == [summary]
    assert await board_messages(theirs.scope().tenant_id) == 0

    # control: the workspace that owns the summary gets its board
    own = await brain_visual_queue.attach_board(
        business_db, mine.scope(), settings, mine_conversation, [summary], "en"
    )
    assert len(own) > 1
    assert await board_messages(mine.scope().tenant_id) > 0
