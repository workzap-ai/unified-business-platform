"""Native bookings, tasks and tickets: availability, concurrency, idempotency, customer
binding, opt-in defaults and the service-conversation action path (AI mocked)."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import mock_turns, turn
from test_service_lifecycle import create

from app.modules.pi.tools.base import PI_RUNTIME_PERMISSIONS
from app.modules.pi.tools.registry import ToolRegistry
from app.modules.pi_saas import work
from app.modules.pi_saas.models import PiBookableService, PiBooking, PiTicket
from app.shared.errors import BusinessRuleViolation, ResourceNotFound
from app.shared.scope import WorkspaceScope

pytestmark = pytest.mark.integration

ALL_DAY = {d: [["00:00", "23:59"]] for d in work.DAY_KEYS}


def system(tenant: str, environment: str) -> WorkspaceScope:
    return WorkspaceScope.system(UUID(tenant), UUID(environment), PI_RUNTIME_PERMISSIONS, "PI")


async def test_concurrent_requests_for_one_slot_book_it_once(live_stack):
    async with live_stack.browser() as browser:
        owner = await live_stack.register(browser)
        await owner.create("products/pi/install", {})
        await owner.ok("PUT", "products/pi/environment", {"enabled": True})
        service = await owner.create(
            "pi/bookable-services",
            {
                "name": "Consultation",
                "duration_minutes": 60,
                "buffer_minutes": 15,
                "working_hours": ALL_DAY,
            },
        )
        customer = await owner.create("customers", {"name": "Booking customer", "tags": []})
    scope = system(owner.tenant_id, owner.environment_id)
    sessions = live_stack.app.state.sessions
    async with sessions() as session:
        row = await session.get(PiBookableService, UUID(service["id"]))
        slots = await work.available_slots(session, scope, row, "UTC")
    start = datetime.fromisoformat(slots[0]["start"])

    async def attempt(key: str) -> str:
        async with sessions() as session:
            try:
                booking = await work.book(
                    session,
                    scope,
                    service_id=UUID(service["id"]),
                    customer_id=UUID(customer["id"]),
                    conversation_id=None,
                    starts_at=start,
                    timezone="UTC",
                    idempotency_key=key,
                )
                await session.commit()
                return str(booking.id)
            except BusinessRuleViolation as exc:
                await session.rollback()
                return exc.code

    outcomes = await asyncio.gather(*(attempt(f"race-{i}-{uuid4()}") for i in range(4)))
    assert sum(o == "SLOT_UNAVAILABLE" for o in outcomes) == 3, outcomes
    # The same idempotency key returns the same booking instead of failing.
    key = f"retry-{uuid4()}"
    later = datetime.fromisoformat(slots[3]["start"])
    async with sessions() as session:
        first = await work.book(
            session,
            scope,
            service_id=UUID(service["id"]),
            customer_id=UUID(customer["id"]),
            conversation_id=None,
            starts_at=later,
            timezone="UTC",
            idempotency_key=key,
        )
        await session.commit()
    async with sessions() as session:
        again = await work.book(
            session,
            scope,
            service_id=UUID(service["id"]),
            customer_id=UUID(customer["id"]),
            conversation_id=None,
            starts_at=later,
            timezone="UTC",
            idempotency_key=key,
        )
        await session.commit()
        assert again.id == first.id
        # Booked slots and their buffer disappear from availability.
        row = await session.get(PiBookableService, UUID(service["id"]))
        remaining = {s["start"] for s in await work.available_slots(session, scope, row, "UTC")}
        assert slots[0]["start"] not in remaining and slots[3]["start"] not in remaining
        # Another customer can't cancel this booking through the customer-bound path.
        with pytest.raises(ResourceNotFound):
            await work.cancel_booking(session, scope, first.id, uuid4())


async def _bookable(api, pi) -> tuple[dict, list[dict]]:
    service = await create(
        api,
        "pi/bookable-services",
        {"name": "Discovery call", "duration_minutes": 30, "working_hours": ALL_DAY},
    )
    for tool in (
        "check_availability",
        "create_booking",
        "cancel_booking",
        "get_bookings",
        "create_ticket",
        "create_task",
    ):
        response = await api.put(f"/api/v1/pi/tools/{tool}/enabled", json={"enabled": True})
        assert response.status_code == 200, response.text
    scope = system(pi.tenant_id, pi.environment_id)
    row = await pi.db.get(PiBookableService, UUID(service["id"]))
    return service, await work.available_slots(pi.db, scope, row, "UTC", limit=6)


async def test_new_work_tools_are_opt_in(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    try:
        enabled = await ToolRegistry(business_db).enabled_tools(
            system(pi.tenant_id, pi.environment_id), None
        )
        assert not enabled & {"create_booking", "create_ticket", "create_task"}
        assert "search_knowledge_base" in enabled
    finally:
        await pi.close()


async def test_service_conversation_books_only_an_offered_agreed_slot(
    api, business_db, monkeypatch
):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    try:
        service, slots = await _bookable(api, pi)
        invented = (datetime.now(UTC) + timedelta(days=2)).replace(minute=7).isoformat()
        mock_turns(
            monkeypatch,
            # Offers times (verbatim labels are allowed through the no-price guard).
            turn(reply=f"I can do {slots[0]['label']} or {slots[1]['label']}. Which suits you?"),
            # An invented time is never booked, even with agreement.
            turn(
                reply="Let me check that.",
                action="booking",
                booking_service_id=service["id"],
                booking_start=invented,
                action_evidence="yes please",
            ),
            # No explicit agreement in the latest message: nothing is booked.
            turn(
                reply="Great.",
                action="booking",
                booking_service_id=service["id"],
                booking_start=slots[0]["start"],
                action_evidence="the first one",
            ),
            # Explicit agreement to an offered slot: booked and confirmed by the tool.
            turn(
                reply="Perfect, noting that for you.",
                action="booking",
                booking_service_id=service["id"],
                booking_start=slots[0]["start"],
                action_evidence="the first one works",
            ),
        )
        await pi.process("Can I book a discovery call?", "book-1")
        first_reply = await pi.reply_to("book-1")
        assert slots[0]["label"] in first_reply.body
        await pi.process("yes please, the 7 minute slot", "book-2")
        await pi.process("hmm maybe", "book-3")
        mine = PiBooking.tenant_id == UUID(pi.tenant_id)
        assert (
            await business_db.scalar(select(func.count()).select_from(PiBooking).where(mine)) == 0
        )
        await pi.process("Yes, the first one works for me", "book-4")
        booking = await business_db.scalar(select(PiBooking).where(mine))
        assert booking is not None and booking.status == "confirmed"
        assert booking.starts_at == datetime.fromisoformat(slots[0]["start"])
        confirmation = await pi.reply_to("book-4")
        assert confirmation.body.endswith(f"✓ {slots[0]['label']} (UTC)")
    finally:
        await pi.close()


async def test_service_conversation_logs_one_ticket_for_a_problem(api, business_db, monkeypatch):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    try:
        await _bookable(api, pi)
        mock_turns(
            monkeypatch,
            turn(
                reply="Sorry about that. Our team will look into it.",
                action="ticket",
                action_subject="Contact form not sending",
                action_priority="high",
            ),
        )
        await pi.process("The contact form on my new site is broken", "ticket-1")
        tickets = list(
            await business_db.scalars(
                select(PiTicket).where(PiTicket.tenant_id == UUID(pi.tenant_id))
            )
        )
        assert len(tickets) == 1 and tickets[0].priority == "high"
        assert tickets[0].first_response_due_at is not None
        listed = (await api.get("/api/v1/pi/tickets")).json()
        assert [t["subject"] for t in listed] == ["Contact form not sending"]
    finally:
        await pi.close()
