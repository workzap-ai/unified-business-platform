"""The customer page's "Your solution" (what a paying customer asked for and bought) and
the Activity tab's order (newest first, same-moment events in the order they happened)."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import select
from test_pi_customer_payments import MEEZAN
from test_pi_deals import DEALS, _customer_in_chat, _lead, _price, _public, _send, _token
from test_pi_pipeline import pi_workspace
from test_service_lifecycle import create

from app.modules.billing.models import Invoice
from app.modules.customers.models import Customer, CustomerActivity
from app.modules.orders.models import Order
from app.modules.sales.models import SalesLead

pytestmark = pytest.mark.integration


async def test_paid_deal_shows_as_the_customers_solution(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    put = await api.put(
        "/api/v1/pi/customer-payments/settings",
        json={"bank_enabled": True, "bank_accounts": [MEEZAN]},
    )
    assert put.status_code == 200, put.text
    customer_id, conversation = await _customer_in_chat(pi)
    lead_id = await _lead(pi, customer_id, conversation)
    lead = await business_db.get(SalesLead, UUID(lead_id))
    lead.requirements = {
        **(lead.requirements or {}),
        "problem": "Customers can't find the bakery online",
        "goal": "More walk-in orders",
        "features": ["Logo files", "Five-page site"],
    }
    await business_db.flush()

    # Nothing paid yet: no solution to show.
    empty = await api.get(f"/api/v1/customers/{customer_id}/solution")
    assert empty.status_code == 200, empty.text
    assert empty.json() == {"projects": []}

    made = await api.post(f"{DEALS}/leads/{lead_id}/proposal")
    assert made.status_code == 201, made.text
    quote_id = made.json()["quote_id"]
    await _price(pi, quote_id)
    sent = await api.post(f"{DEALS}/quotes/{quote_id}/send")
    assert sent.status_code == 200, sent.text
    await _send(pi)
    public = _public(api)
    accepted = await public.post(
        f"/api/v1/pi-app/docs/{_token(sent.json()['link'])}/respond", json={"action": "accepted"}
    )
    assert accepted.status_code == 200, accepted.text
    order = await business_db.scalar(select(Order).where(Order.quote_id == UUID(quote_id)))
    invoice = await business_db.scalar(select(Invoice).where(Invoice.order_id == order.id))

    # Accepted and invoiced but not paid: still nothing.
    assert (await api.get(f"/api/v1/customers/{customer_id}/solution")).json()["projects"] == []

    payment = await api.post(
        f"/api/v1/billing/invoices/{invoice.id}/payments",
        json={"amount": "100000.00", "method": "bank_transfer"},
    )
    assert payment.status_code == 201, payment.text
    moved = await api.post(f"{DEALS}/orders/{order.id}/work", json={"step": "start"})
    assert moved.status_code == 200, moved.text
    conversation.service_brief = {
        **(conversation.service_brief or {}),
        "feedback": [
            {
                "project": "Branding for Crescent Bakers",
                "mood": "happy",
                "words": "Going well so far",
                "at": datetime.now(UTC).isoformat(),
            },
            {"project": "Something else entirely", "mood": "unhappy", "words": "Late"},
        ],
    }
    await business_db.flush()

    response = await api.get(f"/api/v1/customers/{customer_id}/solution")
    assert response.status_code == 200, response.text
    [project] = response.json()["projects"]
    assert project["lead_id"] == lead_id
    assert project["title"] == "Branding for Crescent Bakers"
    assert project["notes"]["problem"] == "Customers can't find the bakery online"
    assert project["notes"]["features"] == ["Logo files", "Five-page site"]
    bought = project["bought"]
    assert bought["quote_id"] == quote_id and bought["total"] == "100000.00"
    assert [(line["description"], line["line_total"]) for line in bought["lines"]] == [
        ("Logo", "25000.00"),
        ("Website", "75000.00"),
    ]
    paid = project["payment"]
    assert paid["status"] == "paid" and paid["invoice_number"] == invoice.number
    assert paid["amount_paid"] == "100000.00" and paid["balance"] == "0.00"
    assert paid["paid_at"] is not None
    assert len(paid["receipts"]) == 1 and paid["receipts"][0]["name"].endswith(".pdf")
    delivery = project["delivery"]
    assert delivery["order_number"] == order.number and delivery["order_status"] == "processing"
    assert [(s["key"], s["done"]) for s in delivery["steps"]] == [
        ("paid", True),
        ("work", True),
        ("delivered", False),
    ]
    assert delivery["steps"][1]["at"] is not None
    assert [f["words"] for f in project["feedback"]] == ["Going well so far"]
    assert project["next"]["title"] == "Deliver the work"

    # Each event keeps its own moment (the whole test is one transaction), and the
    # timeline lists them newest first.
    url = f"/api/v1/customers/{customer_id}/activities"
    items = (await api.get(url, params={"page_size": 100})).json()["items"]
    assert len({a["created_at"] for a in items}) == len(items)
    summaries = [a["summary"] for a in items]
    number = bought["quote_number"]
    assert summaries.index(f"Quote {number}: sent → accepted") < summaries.index(
        f"Quote {number} drafted"
    )
    assert summaries.index(f"Order {order.number}: confirmed → processing") == 0


async def test_activity_ties_list_the_later_event_first(api, business_db):
    """Rows logged before the fix share their transaction's time: insert order decides."""
    await pi_workspace(api, business_db, business_type="service_business")
    customer = await create(api, "customers", {"name": "Dalal & Co", "phone": "+15550000077"})
    row = await business_db.get(Customer, UUID(customer["id"]))
    same = datetime(2030, 1, 1, 9, 30, tzinfo=UTC)  # newer than "Customer created"
    summaries = [
        "Quote QUO-000008 drafted",
        "Quote QUO-000008: draft → approved",
        "Quote QUO-000008: approved → sent",
    ]
    for summary in summaries:
        business_db.add(
            CustomerActivity(
                tenant_id=row.tenant_id,
                environment_id=row.environment_id,
                customer_id=row.id,
                kind="quote",
                summary=summary,
                actor_label="pi",
                created_at=same,
            )
        )
        await business_db.flush()
    url = f"/api/v1/customers/{customer['id']}/activities"
    page = (await api.get(url)).json()
    assert [a["summary"] for a in page["items"]] == [*summaries[::-1], "Customer created"]
    # Paged one at a time: the same order.
    one = [
        (await api.get(url, params={"page": n, "page_size": 1})).json()["items"][0]["summary"]
        for n in (1, 2, 3, 4)
    ]
    assert one == [*summaries[::-1], "Customer created"]
