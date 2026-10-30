"""Erase gaps G1 to G10 (docs/pi-saas/pi-erase-gaps-g1-g14.md on origin/main): an erase in one
workspace removes
the customer's words from staff notes, tags, tickets, staff requests, handoffs, pending actions,
bookings, tasks and deal documents, and deletes the portal share links scoped to the erased chats,
while another workspace's rows (same phone, colliding ids) are untouched. Links to ALL of a
customer's chats are left alone (erase decision R1 (share links) is open).

Written to run on the disposable database (the integrator runs it under the DB mutex); the static
twin is tests/unit/test_pi_erase_completeness.py."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import ProgrammingError
from test_pi_isolation_core import two_chats

from app.modules.customers.models import Customer
from app.modules.pi.brain_erase import ERASED, erase_customer
from app.modules.pi.models import PiConversation, PiHandoff, PiMessage, PiPendingAction
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
    assert removed["_skipped"] == []  # no step was skipped: success is never silent

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


async def test_share_links_of_the_erased_chats_go_and_all_chat_links_are_left_alone(
    api, business_db, monkeypatch
):
    """Only links scoped to the erased chats are deleted. A link to ALL of a customer's chats has no
    workspace key and spans businesses (erase decision R1 (share links) open): it must stay
    untouched."""
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
            # all of the customer's chats (spans businesses): untouched, erase decision R1 is open
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
    assert (
        links["c"].phone == phone and links["c"].revoked_at is None
    )  # erase decision R1: left untouched
    assert links["d"].phone == other_phone and links["d"].revoked_at is None
    assert result["removed"]["share_links_deleted"] == 1
    assert "share_links_revoked" not in result["removed"]
    assert "share_links_all_chats" in result["kept_reasons"]
    await w.a.close()
    await w.b.close()


async def other_customer_rows(db, conv, tag: str) -> Customer:
    """A second customer of the same workspace with rows linked only by customer_id."""
    where = {"tenant_id": conv.tenant_id, "environment_id": conv.environment_id}
    other = Customer(**where, name=f"Other owner {tag}")
    service = PiBookableService(**where, name=f"Other visit {tag}")
    db.add_all([other, service])
    await db.flush()
    db.add_all(
        [
            PiTicket(**where, customer_id=other.id, subject=f"keep {tag}", summary=f"keep {tag}"),
            PiTask(
                **where,
                title=f"keep {tag}",
                description=f"keep {tag}",
                customer_id=other.id,
                idempotency_key=f"keep-task-{tag}",
            ),
            PiBooking(
                **where,
                service_id=service.id,
                customer_id=other.id,
                starts_at=FUTURE,
                ends_at=FUTURE + timedelta(minutes=30),
                timezone="Asia/Karachi",
                notes=f"keep {tag}",
                idempotency_key=f"keep-bk-{tag}",
            ),
            PiDocument(
                **where,
                kind="proposal",
                customer_id=other.id,
                token_hash=f"keep{tag}".ljust(64, "0"),
                expires_at=FUTURE,
                message_text=f"keep {tag}",
            ),
        ]
    )
    await db.flush()
    return other


async def test_another_customer_in_the_same_workspace_is_untouched(api, business_db, monkeypatch):
    db = business_db
    w = await two_chats(api, db, monkeypatch)
    await seed_rows(db, w.conv_a, "a")
    await other_customer_rows(db, w.conv_a, "x")
    ta = w.conv_a.tenant_id

    await erase_customer(db, w.scope_a, w.cust_a)
    await db.flush()

    for model, column in (
        (PiTicket, "subject"),
        (PiTask, "title"),
        (PiBooking, "notes"),
        (PiDocument, "message_text"),
    ):
        values = await texts(db, model, ta, column)
        assert "keep x" in values, f"{model.__tablename__}: the other customer's words were erased"
        assert not [v for v in values if WORDS in v], model.__tablename__
    await w.a.close()
    await w.b.close()


async def test_a_ticket_and_a_task_linked_only_by_customer_id_are_cleared(
    api, business_db, monkeypatch
):
    db = business_db
    w = await two_chats(api, db, monkeypatch)
    where = {"tenant_id": w.conv_a.tenant_id, "environment_id": w.conv_a.environment_id}
    db.add_all(
        [
            PiTicket(**where, customer_id=w.cust_a, subject=WORDS, summary=WORDS),
            PiTask(
                **where,
                title=WORDS,
                description=WORDS,
                customer_id=w.cust_a,
                idempotency_key="only-by-customer",
            ),
        ]
    )
    await db.flush()

    await erase_customer(db, w.scope_a, w.cust_a)
    await db.flush()

    ta = w.conv_a.tenant_id
    assert await count(db, PiTicket, tenant_id=ta) == 1  # the row stays
    assert await count(db, PiTask, tenant_id=ta) == 1  # the task row stays too, blanked
    assert await texts(db, PiTicket, ta, "subject") == [ERASED]  # the title takes the marker
    assert await texts(db, PiTicket, ta, "summary") == [""]  # free text is blanked
    assert [v for v in await texts(db, PiTask, ta, "title", "description") if WORDS in v] == []
    await w.a.close()
    await w.b.close()


async def test_erasing_twice_is_idempotent_and_skips_nothing(api, business_db, monkeypatch):
    db = business_db
    w = await two_chats(api, db, monkeypatch)
    await seed_rows(db, w.conv_a, "a")
    ta = w.conv_a.tenant_id

    first = await erase_customer(db, w.scope_a, w.cust_a)
    await db.flush()
    after_first = await texts(db, PiTicket, ta, "subject", "summary")
    assert after_first == [ERASED, ""]  # subject: the marker, summary: blank
    second = await erase_customer(db, w.scope_a, w.cust_a)
    await db.flush()

    assert first["removed"]["_skipped"] == [] and second["removed"]["_skipped"] == []
    assert await texts(db, PiTicket, ta, "subject", "summary") == after_first
    assert not [v for v in after_first if WORDS in v]
    assert second["removed"]["conversation_tags"] == 0  # nothing left to delete
    assert second["removed"]["pending_actions"] == 0
    await w.a.close()
    await w.b.close()


async def test_a_confirmed_pending_action_keeps_its_row_with_blank_text(
    api, business_db, monkeypatch
):
    db = business_db
    w = await two_chats(api, db, monkeypatch)
    where = {"tenant_id": w.conv_a.tenant_id, "environment_id": w.conv_a.environment_id}
    db.add_all(
        [
            PiPendingAction(
                **where,
                conversation_id=w.conv_a.id,
                kind="confirm_order",
                status="confirmed",
                payload={"text": WORDS},
                summary=WORDS,
                expires_at=FUTURE,
                resolved_at=datetime.now(UTC),
            ),
            PiPendingAction(
                **where,
                conversation_id=w.conv_a.id,
                kind="confirm_order",
                status="pending",
                payload={"text": WORDS},
                summary=WORDS,
                expires_at=FUTURE,
            ),
        ]
    )
    await db.flush()

    result = await erase_customer(db, w.scope_a, w.cust_a)
    await db.flush()
    db.expire_all()

    rows = list(
        await db.scalars(
            select(PiPendingAction).where(PiPendingAction.tenant_id == where["tenant_id"])
        )
    )
    assert [r.status for r in rows] == ["confirmed"]  # the unresolved draft is deleted
    assert rows[0].payload == {} and rows[0].summary == ""  # the audit row stays, blanked
    assert result["removed"]["pending_actions"] == 1
    assert result["removed"]["pending_actions_cleared"] == 1
    await w.a.close()
    await w.b.close()


async def test_another_customers_staff_requests_and_handoffs_in_the_same_workspace_are_untouched(
    api, business_db, monkeypatch
):
    """Staff requests and handoffs are filtered by customer_id only: a second customer of the same
    workspace, with its own chat, must keep both."""
    db = business_db
    w = await two_chats(api, db, monkeypatch)
    await seed_rows(db, w.conv_a, "a")
    # read what is needed before the session expires its objects (no lazy load outside a greenlet)
    ta, conv_a_id = w.conv_a.tenant_id, w.conv_a.id
    await w.a.process("hello", "other-customer", sender="923001112233")
    await w.a.deliver_all()
    db.expire_all()
    other_conv = await db.scalar(
        select(PiConversation).where(PiConversation.tenant_id == ta, PiConversation.id != conv_a_id)
    )
    assert other_conv is not None and other_conv.customer_id != w.cust_a
    where = {"tenant_id": other_conv.tenant_id, "environment_id": other_conv.environment_id}
    db.add_all(
        [
            PiStaffRequest(
                **where,
                conversation_id=other_conv.id,
                customer_id=other_conv.customer_id,
                question="keep question",
                context_summary="keep context",
                answer="keep answer",
            ),
            PiHandoff(
                **where,
                conversation_id=other_conv.id,
                customer_id=other_conv.customer_id,
                reason="customer_request",
                created_by_label="pi",
                summary="keep summary",
                resolution_note="keep note",
            ),
        ]
    )
    await db.flush()

    await erase_customer(db, w.scope_a, w.cust_a)
    await db.flush()

    assert "keep question" in await texts(db, PiStaffRequest, ta, "question")
    assert "keep answer" in await texts(db, PiStaffRequest, ta, "answer")
    assert "keep summary" in await texts(db, PiHandoff, ta, "summary")
    assert "keep note" in await texts(db, PiHandoff, ta, "resolution_note")
    assert not [v for v in await texts(db, PiStaffRequest, ta, "question") if WORDS in v]
    await w.a.close()
    await w.b.close()


class PgError(Exception):
    """A driver error carrying a SQLSTATE that is not 'undefined table'."""

    def __init__(self, sqlstate: str) -> None:
        super().__init__("db error")
        self.sqlstate = sqlstate


async def test_a_failing_step_rolls_every_earlier_step_back_with_the_request(
    api, business_db, monkeypatch
):
    """Only an undefined table is skipped. Any other error propagates, so the request's transaction
    rolls back and nothing is committed: no partial erase after a 'delete everything' request."""
    db = business_db
    w = await two_chats(api, db, monkeypatch)
    await seed_rows(db, w.conv_a, "a")
    # read what is needed before anything expires (no lazy load outside a greenlet)
    ta, conv_a_id = w.conv_a.tenant_id, w.conv_a.id
    real_execute = db.execute

    async def failing(statement, *args, **kwargs):
        if str(statement).lstrip().startswith("UPDATE pi_tasks"):
            raise ProgrammingError(str(statement), {}, PgError("42703"))  # undefined column
        return await real_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", failing)
    with pytest.raises(ProgrammingError):
        async with db.begin_nested():  # stands for the request's transaction
            await erase_customer(db, w.scope_a, w.cust_a)
    monkeypatch.setattr(db, "execute", real_execute)

    # nothing of the erase survived: the earlier steps were rolled back with the failing one
    assert await texts(db, PiTicket, ta, "subject") == [f"{WORDS} a"]
    assert await count(db, PiConversationTag, tenant_id=ta) == 1
    bodies = [
        row
        for row in await db.scalars(
            select(PiMessage.body).where(PiMessage.conversation_id == conv_a_id)
        )
    ]
    assert bodies and ERASED not in bodies
    await w.a.close()
    await w.b.close()
