"""Erase gaps G1 to G10 (docs/pi-saas/pi-erase-gaps-g1-g14.md): an erase in one workspace removes
the customer's words from staff notes, tags, tickets, staff requests, handoffs, pending actions,
bookings, tasks and deal documents, and takes the phone off the portal share links, while another
workspace's rows (same phone, colliding ids) are untouched.

Written to run on the disposable database (the integrator runs it under the DB mutex); the static
twin is tests/unit/test_pi_erase_completeness.py."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from test_pi_isolation_core import two_chats

from app.modules.customers.models import Customer
from app.modules.pi.brain_erase import ERASED, erase_customer
from app.modules.pi.models import PiHandoff, PiPendingAction
from app.modules.pi_customer.models import CustomerShareLink
from app.modules.pi_saas.deal_models import PiDocument
from app.modules.pi_saas.models import (
    PiBookableService,
    PiBooking,
    PiConversationNote,
    PiConversationTag,
    PiStaffRequest,
    PiTask,
    PiTicket,
)

pytestmark = pytest.mark.integration

WORDS = "my shop stock runs out"
FUTURE = datetime.now(UTC) + timedelta(days=7)


def digits(customer: Customer) -> str:
    raw = customer.phone or customer.whatsapp_id or ""
    return "".join(ch for ch in raw if ch.isdigit())


async def seed_rows(db, conv, tag: str) -> SimpleNamespace:
    """One row of every G1 to G10 table for this conversation, each holding customer words."""
    where = {"tenant_id": conv.tenant_id, "environment_id": conv.environment_id}
    cid = conv.customer_id
    service = PiBookableService(**where, name=f"Visit {tag}")
    db.add(service)
    await db.flush()
    db.add_all(
        [
            PiConversationNote(
                **where, conversation_id=conv.id, author_label="staff", body=f"{WORDS} {tag}"
            ),
            PiConversationTag(**where, conversation_id=conv.id, tag=f"vip-{tag}"),
            PiTicket(
                **where,
                customer_id=cid,
                conversation_id=conv.id,
                subject=f"{WORDS} {tag}",
                summary=f"{WORDS} {tag}",
            ),
            PiStaffRequest(
                **where,
                conversation_id=conv.id,
                customer_id=cid,
                question=f"{WORDS} {tag}",
                context_summary=f"{WORDS} {tag}",
                answer=f"{WORDS} {tag}",
            ),
            PiHandoff(
                **where,
                conversation_id=conv.id,
                customer_id=cid,
                reason="customer_request",
                created_by_label="pi",
                summary=f"{WORDS} {tag}",
                resolution_note=f"{WORDS} {tag}",
            ),
            PiPendingAction(
                **where,
                conversation_id=conv.id,
                kind="confirm_order",
                payload={"text": f"{WORDS} {tag}"},
                summary=f"{WORDS} {tag}",
                expires_at=FUTURE,
            ),
            PiBooking(
                **where,
                service_id=service.id,
                customer_id=cid,
                conversation_id=conv.id,
                starts_at=FUTURE,
                ends_at=FUTURE + timedelta(minutes=30),
                timezone="Asia/Karachi",
                notes=f"{WORDS} {tag}",
                idempotency_key=f"bk-{tag}",
            ),
            PiTask(
                **where,
                title=f"{WORDS} {tag}",
                description=f"{WORDS} {tag}",
                customer_id=cid,
                conversation_id=conv.id,
                customer_visible_status=f"{WORDS} {tag}",
                idempotency_key=f"task-{tag}",
            ),
            PiDocument(
                **where,
                kind="proposal",
                customer_id=cid,
                conversation_id=conv.id,
                token_hash=f"{tag}".ljust(64, "0"),
                expires_at=FUTURE,
                message_text=f"{WORDS} {tag}",
                response_note=f"{WORDS} {tag}",
            ),
        ]
    )
    await db.flush()
    return SimpleNamespace(where=where)


async def count(db, model, **filters) -> int:
    db.expire_all()
    query = select(func.count()).select_from(model)
    for key, value in filters.items():
        query = query.where(getattr(model, key) == value)
    return int(await db.scalar(query) or 0)


async def texts(db, model, tenant_id, *columns) -> list[str]:
    db.expire_all()
    rows = await db.execute(
        select(*(getattr(model, c) for c in columns)).where(model.tenant_id == tenant_id)
    )
    return [str(value) for row in rows for value in row if value is not None]


async def test_erasing_a_customer_clears_the_words_and_keeps_another_workspace(
    api, business_db, monkeypatch
):
    db = business_db
    w = await two_chats(api, db, monkeypatch)
    await seed_rows(db, w.conv_a, "a")
    await seed_rows(db, w.conv_b, "b")
    ta, tb = w.conv_a.tenant_id, w.conv_b.tenant_id

    result = await erase_customer(db, w.scope_a, w.cust_a)
    await db.flush()
    removed = result["removed"]

    # G2, G6: rows with no record value are deleted
    assert await count(db, PiConversationTag, tenant_id=ta) == 0
    assert await count(db, PiPendingAction, tenant_id=ta) == 0
    assert removed["conversation_tags"] == 1 and removed["pending_actions"] == 1
    # G1, G3, G4, G5, G7, G8, G9: the row stays, the words go
    for model, columns in (
        (PiConversationNote, ("body",)),
        (PiTicket, ("subject", "summary")),
        (PiStaffRequest, ("question", "context_summary", "answer")),
        (PiHandoff, ("summary", "resolution_note")),
        (PiBooking, ("notes",)),
        (PiTask, ("title", "description", "customer_visible_status")),
        (PiDocument, ("message_text", "response_note")),
    ):
        assert await count(db, model, tenant_id=ta) == 1, model.__tablename__
        for value in await texts(db, model, ta, *columns):
            assert WORDS not in value, f"{model.__tablename__} still holds the customer's words"
    assert (await texts(db, PiTicket, ta, "subject")) == [ERASED]

    # workspace B (same phone): nothing changed, nothing deleted
    assert await count(db, PiConversationTag, tenant_id=tb) == 1
    assert await count(db, PiPendingAction, tenant_id=tb) == 1
    for model, column in (
        (PiConversationNote, "body"),
        (PiTicket, "subject"),
        (PiStaffRequest, "question"),
        (PiHandoff, "summary"),
        (PiBooking, "notes"),
        (PiTask, "title"),
        (PiDocument, "message_text"),
    ):
        assert (await texts(db, model, tb, column)) == [f"{WORDS} b"], model.__tablename__
    await w.a.close()
    await w.b.close()


async def test_share_links_of_the_erased_chats_go_and_the_phone_leaves_all_chat_links(
    api, business_db, monkeypatch
):
    db = business_db
    w = await two_chats(api, db, monkeypatch)
    cust_a = await db.get(Customer, w.cust_a)
    phone = digits(cust_a)
    assert phone  # the same number texts both workspaces
    other_phone = "923001234567"
    db.add_all(
        [
            # scoped to A's chat: deleted
            CustomerShareLink(
                phone=phone, token_hash="a" * 64, conversation_id=w.conv_a.id, expires_at=FUTURE
            ),
            # scoped to B's chat (same phone): untouched
            CustomerShareLink(
                phone=phone, token_hash="b" * 64, conversation_id=w.conv_b.id, expires_at=FUTURE
            ),
            # all of the customer's chats (spans businesses): revoked and the phone removed
            CustomerShareLink(
                phone=phone, token_hash="c" * 64, conversation_id=None, expires_at=FUTURE
            ),
            # somebody else's all-chat link: untouched
            CustomerShareLink(
                phone=other_phone, token_hash="d" * 64, conversation_id=None, expires_at=FUTURE
            ),
        ]
    )
    await db.flush()

    result = await erase_customer(db, w.scope_a, w.cust_a)
    await db.flush()
    db.expire_all()
    links = {link.token_hash[0]: link for link in await db.scalars(select(CustomerShareLink))}
    assert "a" not in links  # the link to the erased chat is gone
    assert links["b"].phone == phone and links["b"].revoked_at is None  # B's chat link stays
    assert links["c"].phone != phone and links["c"].revoked_at is not None  # cross-business effect
    assert links["d"].phone == other_phone and links["d"].revoked_at is None
    assert result["removed"]["share_links_deleted"] == 1
    assert result["removed"]["share_links_revoked"] == 1
    assert all(phone not in link.phone for link in links.values() if link.token_hash[0] == "c")
    await w.a.close()
    await w.b.close()
