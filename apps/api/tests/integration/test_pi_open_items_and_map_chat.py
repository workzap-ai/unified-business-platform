"""Platform spec v1.4, 17.7 (open items, HO2, HO5, A43) and 4.5 (map editing by chat, G47) on the
real database and webhook flow; the AI and WhatsApp are mocked."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from test_pi_brain_problems import adaptive, create, problems_of, say, workspace
from test_pi_management import member_client
from test_pi_service_conversations import turn

from app.modules.pi import map_builder
from app.modules.pi.models import PiMessage
from app.modules.pi.open_item_models import PiOpenItem
from app.modules.pi.problem_models import PiProblem, PiProblemLink, PiProblemRevision
from app.modules.pi_saas.models import PiStaffRequest

pytestmark = pytest.mark.integration

OPEN = "/api/v1/pi/open-items"
HELLO = "Hi, I'm pi, an AI from Workzap."


def script(context, n):
    said = context["latest_customer_message"]
    if "Best-sellers" in said:
        return turn(
            reply=f"{HELLO} That sounds costly. Which shop feels it most?",
            language="en",
            problem_ops=[
                create("Best-sellers run out", "Best-sellers run out.", "stock_inventory"),
                create("Cashiers are late", "Cashiers are late.", "cash_collections"),
            ],
        )
    if "quote" in said:
        return turn(
            reply="The quote will say how long it takes. Which shop first?",
            language="en",
            problem_ops=[],
        )
    if "delivery fee" in said:
        return turn(
            reply="I do not have that to hand. Which area do you deliver to?",
            language="en",
            knowledge_gaps=["delivery fee for Lahore"],
        )
    return turn(reply="Okay. What else gets in the way?", language="en")


async def two_problems(api, db, monkeypatch):
    adaptive(monkeypatch, script)
    pi = await workspace(api, db)
    await say(pi, "Best-sellers run out and cashiers are late", "oi-1")
    conversation, rows = await problems_of(db, pi)
    assert len(rows) == 2
    return pi, conversation, rows


async def items(db):
    db.expire_all()
    return list(await db.scalars(select(PiOpenItem).order_by(PiOpenItem.created_at)))


def last_reply(pi):
    return next(m["text"]["body"] for m in reversed(pi.sent) if "text" in m)


async def test_a_request_the_reply_ignored_stays_open_past_three_replies_until_addressed(
    api, business_db, monkeypatch
):
    pi, conversation, _ = await two_problems(api, business_db, monkeypatch)
    await say(pi, "how long will it take?", "oi-2")
    [item] = await items(business_db)
    assert (item.kind, item.key, item.status) == ("owner_request", "timeline", "open")
    assert item.due_at is not None
    for n in range(5):  # HO5: more than the old three replies
        await say(pi, f"ok {n}", f"oi-ok-{n}")
        print("DBG2", n, [(m["type"], (m.get("text") or {}).get("body")) for m in pi.sent[-2:]])
    [item] = await items(business_db)
    assert item.status == "open", (item.closed_reason, item.key)
    business_db.expire_all()
    await business_db.refresh(conversation)
    assert [e["kind"] for e in conversation.service_brief["open_requests"]] == ["timeline"]
    # a reply that addresses it closes it (spec: answered)
    await say(pi, "what does the quote say?", "oi-quote")
    [item] = await items(business_db)
    assert item.status == "answered" and item.closed_reason == "reply_addressed"
    await pi.close()


async def test_a_question_pi_could_not_answer_is_kept_and_the_owner_can_drop_it(
    api, business_db, monkeypatch
):
    pi, _, _ = await two_problems(api, business_db, monkeypatch)
    await say(pi, "what is the delivery fee?", "oq-1")
    [item] = await items(business_db)
    assert item.kind == "owner_question" and "delivery fee" in item.text
    await say(pi, "ok", "oq-2")
    assert (await items(business_db))[0].status == "open"
    await say(pi, "never mind", "oq-3")
    [item] = await items(business_db)
    assert item.status == "dropped" and item.closed_reason == "owner_dropped"
    await pi.close()


async def test_what_is_open_is_named_first_when_the_owner_returns_after_a_gap(
    api, business_db, monkeypatch
):
    pi, conversation, _ = await two_problems(api, business_db, monkeypatch)
    await say(pi, "how long will it take?", "rt-1")
    ago = timedelta(hours=6)
    await business_db.execute(update(PiMessage).values(created_at=PiMessage.created_at - ago))
    await business_db.flush()
    await say(pi, "wait, one more thing", "rt-2")
    reply = last_reply(pi)
    assert reply.startswith("Your earlier request is still open: “how long will it take”.")
    assert "?" not in reply.split("Which")[0]  # the quoted words carry no question mark
    [item] = await items(business_db)
    assert item.surfaced_at is not None
    # said once on that return, not again on the next message
    await say(pi, "ok then", "rt-3")
    assert "still open" not in last_reply(pi)
    await pi.close()


async def test_the_staff_view_lists_items_and_handoffs_by_age_with_a_colour(
    api, business_db, monkeypatch
):
    pi, conversation, _ = await two_problems(api, business_db, monkeypatch)
    await say(pi, "how long will it take?", "sv-1")
    where = {"tenant_id": conversation.tenant_id, "environment_id": conversation.environment_id}
    request = PiStaffRequest(
        **where,
        conversation_id=conversation.id,
        customer_id=conversation.customer_id,
        question="Owner wants a person",
        kind="human_requested",
    )
    business_db.add(request)
    await business_db.flush()
    await business_db.execute(
        update(PiStaffRequest)
        .where(PiStaffRequest.id == request.id)
        .values(created_at=PiStaffRequest.created_at - timedelta(minutes=45))
    )
    await business_db.flush()
    response = await api.get(OPEN)
    assert response.status_code == 200, response.text
    body = response.json()
    kinds = {i["kind"]: i for i in body["items"]}
    assert kinds["pending_handoff"]["colour"] == "red"  # 45 minutes against 30
    assert kinds["pending_handoff"]["age_minutes"] >= 45
    assert kinds["owner_request"]["colour"] == "green" and kinds["owner_request"]["sla_minutes"]
    assert body["count"] == 2 and body["by_colour"] == {"red": 1, "green": 1}
    assert [i["created_at"] for i in body["items"]] == sorted(
        i["created_at"] for i in body["items"]
    )
    await pi.close()


async def test_the_staff_view_is_permission_checked_and_workspace_scoped(
    api, business_db, monkeypatch
):
    pi, _, _ = await two_problems(api, business_db, monkeypatch)
    await say(pi, "how long will it take?", "ps-1")
    viewer = await member_client(api, "viewer")
    sales = await member_client(api, "sales")
    support = await member_client(api, "support")
    try:
        for client in (viewer, sales):
            refused = await client.get(OPEN)
            assert refused.status_code == 403, refused.text
        allowed = await support.get(OPEN)
        assert allowed.status_code == 200 and allowed.json()["count"] == 1
    finally:
        for client in (viewer, sales, support):
            await client.aclose()
    api.cookies.clear()
    from test_pi_pipeline import pi_workspace

    other = await pi_workspace(api, business_db, number=str(uuid4().int)[:9])
    assert (await api.get(OPEN)).json()["items"] == []
    await other.close()
    await pi.close()


# --- map editing by chat -----------------------------------------------------------------------


async def linked(api, db, monkeypatch):
    pi, conversation, rows = await two_problems(api, db, monkeypatch)
    where = {"tenant_id": conversation.tenant_id, "environment_id": conversation.environment_id}
    link = PiProblemLink(
        **where,
        from_id=rows[0].id,
        to_id=rows[1].id,
        type="causes",
        evidence="pi_inferred",
        status="suggested",
        confidence=0.8,
    )
    db.add(link)
    await db.flush()
    return pi, conversation, rows, link.id


async def test_a_wrong_link_is_removed_and_pi_asks_the_real_connection(
    api, business_db, monkeypatch
):
    pi, conversation, rows, link_id = await linked(api, business_db, monkeypatch)
    await say(pi, "this connection is wrong", "me-1")
    business_db.expire_all()
    link = await business_db.get(PiProblemLink, link_id)
    assert link.status == "rejected"  # the record stays, the map does not draw it
    reply = last_reply(pi)
    assert "What is the real connection between" in reply and reply.rstrip().endswith("?")
    assert reply.count("?") == 1 and "noted" not in reply.lower()
    assert not reply.startswith("Thanks")
    problems, links = await map_builder.current_inputs(
        business_db, _scope(conversation), rows[0].customer_id
    )
    assert map_builder.drawn_links(problems, links) == []
    reasons = (await business_db.scalars(select(PiProblemRevision.reason))).all()
    assert reasons.count("link_rejected") == 2
    # nothing left to remove: the next "wrong link" is the model's to answer
    await say(pi, "this connection is wrong", "me-2")
    assert "real connection" not in last_reply(pi)
    await pi.close()


def _scope(conversation):
    from app.shared.scope import WorkspaceScope

    return WorkspaceScope.system(
        conversation.tenant_id, conversation.environment_id, frozenset(), "test"
    )


async def test_solved_parked_and_first_are_applied_with_a_revision_and_the_reply_goes_on(
    api, business_db, monkeypatch
):
    pi, conversation, rows = await two_problems(api, business_db, monkeypatch)
    await say(pi, "P1 is solved", "mp-1")
    reply = last_reply(pi)
    assert reply.startswith("Good, ") and "is marked as solved" in reply
    assert "What else gets in the way?" in reply  # the model's own reply follows
    await say(pi, "park this problem, the cashiers one", "mp-2")
    await say(pi, "start with P1", "mp-3")
    _, rows = await problems_of(business_db, pi)
    by_number = {p.number: p for p in rows}
    assert by_number[1].status == "resolved"
    assert by_number[2].status == "parked"
    assert "rank:1" in by_number[1].tags
    reasons = (await business_db.scalars(select(PiProblemRevision.reason))).all()
    assert {"resolved", "parked", "ranked"} <= set(reasons)
    # saying the same again changes nothing and adds no revision
    before = len(reasons)
    await say(pi, "P1 is solved", "mp-4")
    assert len((await business_db.scalars(select(PiProblemRevision.reason))).all()) == before
    await pi.close()


async def test_when_it_cannot_tell_which_problem_pi_asks_one_question(
    api, business_db, monkeypatch
):
    pi, _, _ = await two_problems(api, business_db, monkeypatch)
    await say(pi, "this problem is solved", "am-1")
    reply = last_reply(pi)
    assert (
        reply.count("?") == 1 and reply.rstrip().endswith("?") and "which problem" in reply.lower()
    )
    business_db.expire_all()
    statuses = {p.status for p in await business_db.scalars(select(PiProblem))}
    assert "resolved" not in statuses  # nothing was changed on a guess
    await pi.close()
