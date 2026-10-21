"""The team board: pi turns the team's real work into cards (price a proposal, start
paid work, ...), closes them when the work is done, and moving a deal's card moves the
customer's journey. Plus the team's own cards: create, assign, filter."""

from uuid import UUID

import pytest
from sqlalchemy import func, select
from test_pi_customer_payments import MEEZAN
from test_pi_deals import DEALS, _customer_in_chat, _lead, _price, _public, _send, _token
from test_pi_pipeline import pi_workspace

from app.modules.billing.models import Invoice
from app.modules.orders.models import Order
from app.modules.pi.models import PiHandoff, PiMessage
from app.modules.pi_saas import team_board
from app.modules.pi_saas.models import PiStaffRequest, PiTask

pytestmark = pytest.mark.integration

BOARD = "/api/v1/pi/team-board"


def _cards(board: dict, column: str | None = None) -> list[dict]:
    columns = [column] if column else list(board["columns"])
    return [card for c in columns for card in board["columns"][c]]


async def _board(api, **params) -> dict:
    response = await api.get(BOARD, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def _auto_cards(pi) -> int:
    return await pi.db.scalar(
        select(func.count())
        .select_from(PiTask)
        .where(
            PiTask.tenant_id == UUID(pi.tenant_id),
            PiTask.idempotency_key.startswith(team_board.PREFIX),
        )
    )


async def test_the_board_follows_the_deal_and_moving_a_card_moves_the_journey(
    api, business_db, caplog
):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    put = await api.put(
        "/api/v1/pi/customer-payments/settings",
        json={"bank_enabled": True, "bank_accounts": [MEEZAN]},
    )
    assert put.status_code == 200, put.text
    customer_id, conversation = await _customer_in_chat(pi)
    lead_id = await _lead(pi, customer_id, conversation)
    made = await api.post(f"{DEALS}/leads/{lead_id}/proposal")
    assert made.status_code == 201, made.text
    quote_id = made.json()["quote_id"]

    # An unpriced draft is a "price" card for the team, linked to its edit page.
    board = await _board(api)
    [price] = [c for c in _cards(board, "todo") if c["kind"] == "price"]
    assert price["auto"] and price["title"].startswith("Add prices: ")
    assert price["project"] == "Branding for Crescent Bakers"
    assert price["customer"] == {"id": customer_id, "name": "Ayesha Khan"}
    assert price["link"] == f"/quotes/{quote_id}/edit"
    assert price["due_at"] and price["overdue"] is False and price["assignee"] is None

    # The sync is idempotent: the worker and the page running it again add nothing.
    before = await _auto_cards(pi)
    await team_board.sweep(pi.ctx)
    await team_board.sweep(pi.ctx)
    await _board(api)
    assert await _auto_cards(pi) == before

    # Priced and sent: the card closes by itself.
    await _price(pi, quote_id)
    sent = await api.post(f"{DEALS}/quotes/{quote_id}/send")
    assert sent.status_code == 200, sent.text
    await _send(pi)
    board = await _board(api)
    assert [c["id"] for c in _cards(board, "done")] == [price["id"]]
    assert not [c for c in _cards(board, "todo") if c["kind"] == "price"]

    # Accepted and paid: "Start the work" is on the board.
    public = _public(api)
    accepted = await public.post(
        f"/api/v1/pi-app/docs/{_token(sent.json()['link'])}/respond", json={"action": "accepted"}
    )
    assert accepted.status_code == 200, accepted.text
    await public.aclose()
    order = await business_db.scalar(select(Order).where(Order.quote_id == UUID(quote_id)))
    invoice = await business_db.scalar(select(Invoice).where(Invoice.order_id == order.id))
    paid = await api.post(
        f"/api/v1/billing/invoices/{invoice.id}/payments",
        json={"amount": "100000.00", "method": "bank_transfer"},
    )
    assert paid.status_code == 201, paid.text
    await _send(pi)
    pi.sent.clear()
    board = await _board(api)
    [start] = [c for c in _cards(board, "todo") if c["kind"] == "start"]
    assert start["title"] == "Start the work: Branding for Crescent Bakers"
    assert start["link"] == f"/sales/leads/{lead_id}"

    # Dragging it to In progress starts the work: pi tells the customer, as the deal
    # page's button does, and the deal's "Deliver" card takes its place.
    moved = await api.patch(f"{BOARD}/tasks/{start['id']}", json={"status": "in_progress"})
    assert moved.status_code == 200, moved.text
    await business_db.refresh(order)
    assert order.status == "processing"
    queued = await business_db.scalar(
        select(PiMessage).where(
            PiMessage.tenant_id == UUID(pi.tenant_id),
            PiMessage.idempotency_key == f"pi-order-started:{order.id}",
        )
    )
    assert queued is not None
    texts = await _send(pi)
    assert texts == [
        "Good news Ayesha: work on Branding for Crescent Bakers has started. "
        "We'll keep you posted here."
    ]
    board = await _board(api)
    [deliver] = [c for c in _cards(board, "doing") if c["kind"] == "deliver"]
    assert deliver["title"] == "Deliver: Branding for Crescent Bakers"
    assert start["id"] in [c["id"] for c in _cards(board, "done")]

    # Done on the board = delivered: pi tells the customer and asks how it went.
    moved = await api.patch(f"{BOARD}/tasks/{deliver['id']}", json={"status": "done"})
    assert moved.status_code == 200, moved.text
    await business_db.refresh(order)
    assert order.status == "delivered"
    texts = await _send(pi)
    assert texts[-1].startswith("Branding for Crescent Bakers is delivered Ayesha.")
    assert "pi_team_board_source_failed" not in caplog.text
    await pi.close()


async def test_chats_handed_to_a_person_and_pi_questions_become_cards(api, business_db, caplog):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    customer_id, conversation = await _customer_in_chat(pi)
    scope = {"tenant_id": UUID(pi.tenant_id), "environment_id": UUID(pi.environment_id)}
    handoff = PiHandoff(
        **scope,
        conversation_id=conversation.id,
        customer_id=UUID(customer_id),
        reason="customer_request",
        summary="Wants to talk to a person about a refund",
        created_by_label="pi",
    )
    question = PiStaffRequest(
        **scope,
        conversation_id=conversation.id,
        customer_id=UUID(customer_id),
        question="Do you deliver to Islamabad?",
    )
    business_db.add_all([handoff, question])
    await business_db.flush()

    board = await _board(api)
    assert "pi_team_board_source_failed" not in caplog.text
    todo = {c["kind"]: c for c in _cards(board, "todo")}
    assert todo["reply"]["title"] == "Reply to Ayesha Khan"
    assert todo["reply"]["priority"] == "urgent"
    assert todo["reply"]["link"] == f"/pi/inbox?conversation={conversation.id}"
    assert todo["request"]["title"] == "Answer pi: Do you deliver to Islamabad?"
    assert todo["request"]["link"] == f"/pi/requests?request={question.id}"

    # Answered on the request desk: its card closes by itself.
    question.status = "answered"
    await business_db.flush()
    board = await _board(api)
    assert todo["request"]["id"] in [c["id"] for c in _cards(board, "done")]
    await pi.close()


async def test_the_team_adds_assigns_and_filters_its_own_cards(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    customer_id, _ = await _customer_in_chat(pi)
    made = await api.post(
        f"{BOARD}/tasks",
        json={
            "title": "Call the printer about the banner",
            "description": "Ask for a proof by Friday",
            "customer_id": customer_id,
            "priority": "high",
        },
    )
    assert made.status_code == 201, made.text
    card = made.json()
    assert card["kind"] == "task" and card["auto"] is False and card["column"] == "todo"
    assert card["customer"]["name"] == "Ayesha Khan"
    assert card["link"] == f"/customers/{customer_id}"

    board = await _board(api, who="unassigned")
    me = board["me"]
    assert me in [m["id"] for m in board["members"]]
    assert card["id"] in [c["id"] for c in _cards(board)]
    assert (await _board(api, who="me"))["columns"]["todo"] == []

    assigned = await api.patch(f"{BOARD}/tasks/{card['id']}", json={"assignee_user_id": me})
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["assignee"]["id"] == me
    assert card["id"] in [c["id"] for c in _cards(await _board(api, who="me"))]
    assert card["id"] not in [c["id"] for c in _cards(await _board(api, who="unassigned"))]
    assert [c["id"] for c in _cards(await _board(api, kind="task"))] == [card["id"]]
    assert _cards(await _board(api, kind="price")) == []

    # Someone who isn't on the team can't be given a card.
    stranger = await api.patch(
        f"{BOARD}/tasks/{card['id']}",
        json={"assignee_user_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert stranger.status_code == 422

    waiting = await api.patch(f"{BOARD}/tasks/{card['id']}", json={"status": "blocked"})
    assert waiting.status_code == 200 and waiting.json()["column"] == "waiting"
    board = await _board(api)
    assert board["counts"]["waiting"] == 1 and board["counts"]["mine"] == 1
    done = await api.patch(f"{BOARD}/tasks/{card['id']}", json={"status": "done"})
    assert done.status_code == 200 and done.json()["column"] == "done"
    await pi.close()


async def test_the_pi_app_has_the_team_board(api):
    from pi_saas_support import FakeProvider, configure, pi_client, pi_register

    app = api._transport.app  # type: ignore[attr-defined]
    configure(app, FakeProvider())
    client = pi_client(app)
    await pi_register(client)
    client.headers["x-csrf-token"] = client.cookies["pi_csrf"]
    made = await client.post(
        "/api/v1/pi-app/pi/team-board/tasks", json={"title": "Order new business cards"}
    )
    assert made.status_code == 201, made.text
    board = await client.get("/api/v1/pi-app/pi/team-board")
    assert board.status_code == 200, board.text
    assert [c["title"] for c in board.json()["columns"]["todo"]] == ["Order new business cards"]
    await client.aclose()
