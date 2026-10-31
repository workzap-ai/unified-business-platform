"""PS-8 context memory on the disposable database: two workspaces and two customers (nothing
leaks), an erased customer, a returning owner with a document in each state, the B2a columns
absent (migration 0053 down), a correction history, caps, a failing sub-query, no writes."""

import importlib.util
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import event, select, text
from test_pi_isolation_core import PHONE, problem, two_chats

from app.modules.customers.models import CustomerFile
from app.modules.pi import brain_erase
from app.modules.pi import context_memory as cm
from app.modules.pi.box_models import PiOfferLog, PiSolutionBox
from app.modules.pi.brain_docs_models import PiBrainDocument, PiBrainPayment
from app.modules.pi.business_profile_models import PiBusinessProfile, PiProfileFact
from app.modules.pi.context_memory_types import Limits
from app.modules.pi.models import PiConversation, PiMemory, PiMessage
from app.modules.pi.problem_models import PiProblemRevision
from app.modules.pi.solution_models import PiIdeaArm, PiSolutionMemory
from app.modules.pi_saas.deal_models import PiDocument

pytestmark = pytest.mark.integration

NEW = ("constraints", "tried", "cause", "expected_outcome")
MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "0053_pi_problem_requirements.py"
)
NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


def tag(scope):
    return dict(tenant_id=scope.tenant_id, environment_id=scope.environment_id)


def owner_msg(scope, conv_id, body, minutes, mtype="text", sender="customer", direction="inbound"):
    return PiMessage(
        **tag(scope),
        conversation_id=conv_id,
        direction=direction,
        sender_type=sender,
        message_type=mtype,
        body=body,
        status="received" if direction == "inbound" else "sent",
        created_at=NOW + timedelta(minutes=minutes),
    )


async def present_columns(db):
    rows = await db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'pi_problems' AND table_schema = current_schema()"
        )
    )
    return {r[0] for r in rows}


async def migrate(db, which):
    spec = importlib.util.spec_from_file_location("m0053_ctx", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    def go(sync_connection):
        with Operations.context(MigrationContext.configure(sync_connection)):
            getattr(module, which)()

    await (await db.connection()).run_sync(go)


async def seed_a(db, w):
    """Everything a returning owner of workspace A has: chats, problems, a correction, a document
    in each state, payments, a box, a file, an idea rejected, a profile and a memory."""
    scope, cust, conv = w.scope_a, w.cust_a, w.conv_a
    older = PiConversation(
        **tag(scope),
        customer_id=cust,
        connection_id=conv.connection_id,
        contact_wa_id=PHONE,
        status="closed",
        last_message_at=NOW - timedelta(days=30),
        language="roman_ur",
    )
    db.add(older)
    await db.flush()
    db.add_all(
        [
            owner_msg(scope, older.id, "pichli dafa maine flyers try kiya tha", -60 * 24 * 30),
            owner_msg(scope, older.id, "mujhe yeh nahi chahiye", -60 * 24 * 30 + 1),
            owner_msg(
                scope, older.id, "pi says hi", -60 * 24 * 30 + 2, sender="ai", direction="outbound"
            ),
            owner_msg(scope, conv.id, "my budget is 30k", 0),
            owner_msg(scope, conv.id, "voice note transcript about orders", 1, mtype="audio"),
            owner_msg(scope, conv.id, "a photo", 2, mtype="image"),
            owner_msg(
                scope,
                conv.id,
                "pi reply must never be a fact",
                3,
                sender="ai",
                direction="outbound",
            ),
        ]
    )
    p1 = problem(scope, cust, 1, "Orders get lost")
    p1.source_message_ids = ["m-1"]
    p1.systems_mentioned = ["Excel"]
    p1.scope = {"where": "Lahore shop"}
    p1.constraints = {"budget": {"text": "50k", "msg": "m2"}, "staff": {"text": "two people"}}
    p1.tried = [{"what": "WhatsApp groups", "outcome": "got messy", "msg": "m1"}]
    p1.cause = {"text": "no tracking", "status": "owner_said", "evidence": {"words": ["tracking"]}}
    p1.expected_outcome = "no lost orders"
    p1.revision = 3
    p2 = problem(scope, cust, 2, "Stock runs out")
    p2.cause = {"text": "supplier late", "status": "pi_inferred"}
    p2.status = "draft"
    db.add_all([p1, p2])
    await db.flush()
    db.add_all(
        [
            PiProblemRevision(
                **tag(scope),
                problem_id=p1.id,
                revision=1,
                reason="created",
                by="pi",
                diff={"constraints": [None, {"budget": {"text": "30k", "msg": "m1"}}]},
            ),
            PiProblemRevision(
                **tag(scope),
                problem_id=p1.id,
                revision=2,
                reason="correction",
                by="person",
                diff={
                    "constraints": [
                        {"budget": {"text": "30k", "msg": "m1"}},
                        {"budget": {"text": "50k", "msg": "m2"}},
                    ]
                },
            ),
            PiProblemRevision(
                **tag(scope),
                problem_id=p1.id,
                revision=3,
                reason="correction",
                by="person",
                diff={"title": ["Orders lost", "Orders get lost"]},
            ),
        ]
    )
    states = ["draft", "in_review", "approved", "sent", "superseded"]
    quotes = []
    for i, state in enumerate(states, start=1):
        for kind in ("solution", "quote"):
            doc = PiBrainDocument(
                **tag(scope),
                customer_id=cust,
                conversation_id=conv.id,
                offer_id=uuid4(),
                kind=kind,
                number=i,
                version=1,
                status=state,
                problem_ids=[str(p1.id)],
                total=Decimal("100.00") if kind == "quote" else None,
                currency="PKR" if kind == "quote" else "",
                approved_at=NOW if state in ("approved", "sent") else None,
                created_at=NOW + timedelta(minutes=i),
            )
            db.add(doc)
            if kind == "quote":
                quotes.append(doc)
    await db.flush()
    for quote, pstate in zip(
        quotes[:4], ["pending", "claimed", "confirmed", "failed"], strict=True
    ):
        db.add(PiBrainPayment(**tag(scope), customer_id=cust, quote_id=quote.id, status=pstate))
    db.add(
        PiSolutionBox(**tag(scope), customer_id=cust, state="offered", version=1, offered_at=NOW)
    )
    db.add(
        PiOfferLog(
            **tag(scope), conversation_id=conv.id, rule="R1", allowed=False, blocked_reason="no yes"
        )
    )
    db.add(
        PiDocument(
            **tag(scope),
            kind="proposal",
            customer_id=cust,
            conversation_id=conv.id,
            token_hash=uuid4().hex + uuid4().hex,
            expires_at=NOW + timedelta(days=5),
            delivery="sent",
            response="accepted",
        )
    )
    db.add(
        CustomerFile(
            **tag(scope),
            customer_id=cust,
            source="upload",
            name="menu.pdf",
            mime="application/pdf",
            size=3,
            sha256="0" * 64,
            data=b"abc",
            uploaded_by_label="staff",
        )
    )
    arm = PiIdeaArm(
        **tag(scope),
        arm_key=f"k:{uuid4()}",
        industry_key="retail",
        problem_id="x",
        text="Send reminders",
    )
    db.add(arm)
    await db.flush()
    db.add(
        PiSolutionMemory(
            **tag(scope),
            customer_id=cust,
            industry_key="retail",
            problem_id="x",
            idea_arm_id=arm.id,
            given_at=NOW,
            reaction="rejected",
        )
    )
    profile = PiBusinessProfile(
        **tag(scope), customer_id=cust, what_they_do="grocery", city_area="Lahore"
    )
    db.add(profile)
    await db.flush()
    db.add(
        PiProfileFact(
            **tag(scope),
            profile_id=profile.id,
            key="staff_count",
            value="4",
            source="owner",
            confirmed=True,
        )
    )
    db.add(
        PiProfileFact(
            **tag(scope), profile_id=profile.id, key="website", value="x.pk", source="page"
        )
    )
    db.add(
        PiMemory(
            **tag(scope),
            customer_id=cust,
            kind="preference",
            content="prefers voice notes",
            content_hash="h1",
        )
    )
    await db.flush()
    return older, p1, p2


async def seed_b(db, w):
    scope, cust, conv = w.scope_b, w.cust_b, w.conv_b
    db.add(owner_msg(scope, conv.id, "B-SECRET budget is 999", 0))
    b1 = problem(scope, cust, 1, "B-SECRET invoices slow")
    b1.constraints = {"budget": {"text": "B-SECRET 999"}}
    db.add(b1)
    db.add(
        PiMemory(
            **tag(scope),
            customer_id=cust,
            kind="context",
            content="B-SECRET fact",
            content_hash="hb",
        )
    )
    db.add(
        CustomerFile(
            **tag(scope),
            customer_id=cust,
            source="upload",
            name="B-SECRET.pdf",
            mime="x/y",
            size=1,
            sha256="1" * 64,
            data=b"z",
            uploaded_by_label="s",
        )
    )
    await db.flush()


def spy(db):
    statements: list[str] = []

    def before(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    target = db.bind.sync_connection
    event.listen(target, "before_cursor_execute", before)
    return statements, lambda: event.remove(target, "before_cursor_execute", before)


async def test_a_returning_owner_with_every_source(api, business_db, monkeypatch):
    db = business_db
    w = await two_chats(api, db, monkeypatch)
    await db.execute(text("SELECT 1"))
    if not set(NEW) <= await present_columns(db):
        await migrate(db, "upgrade")
    older, p1, p2 = await seed_a(db, w)
    await seed_b(db, w)

    statements, stop = spy(db)
    try:
        b = await cm.build_context(db, w.scope_a, customer_id=w.cust_a, conversation_id=w.conv_a.id)
    finally:
        stop()

    # read only: no INSERT / UPDATE / DELETE / DDL, and the file bytes are never selected
    kinds = {s.lstrip().split(None, 1)[0].upper() for s in statements}
    assert kinds <= {"SELECT", "SAVEPOINT", "RELEASE", "ROLLBACK"}, kinds
    assert not any("customer_files.data" in s for s in statements)

    assert not b.unavailable and b.requirements_available and not b.erased
    assert b.language == "roman_ur" or b.language == "en"

    # (a) owner words only: no pi reply, no image; earlier chat first, current chat flagged
    texts = [m.text for m in b.messages]
    assert "pi says hi" not in texts and "pi reply must never be a fact" not in texts
    assert "a photo" not in texts and "voice note transcript about orders" in texts
    flags = [m.current for m in b.messages]
    assert flags[:2] == [False, False] and all(flags[2:]) and len(flags) >= 4
    assert texts[0] == "pichli dafa maine flyers try kiya tha"

    # (b) problems with every stored field including B2a
    one = next(p for p in b.problems if p.number == 1)
    assert one.budget.text == "50k" and one.staff.text == "two people"
    assert one.tried[0].what == "WhatsApp groups" and one.cause_status == "owner_said"
    assert one.expected_outcome == "no lost orders" and one.systems_mentioned == ("Excel",)
    assert [p.number for p in b.problems] == [1, 2]

    # (c) every document state, exact stored state kept, proposed never implemented
    stored = {(s.kind, s.stored_state) for s in b.solutions}
    for state in ("draft", "in_review", "approved", "sent", "superseded"):
        assert ("document", state) in stored and ("quote", state) in stored
    assert {"awaiting_payment", "payment_claimed", "paid", "payment_failed"} <= {
        s.implementation_status for s in b.solutions if s.kind == "payment"
    }
    assert ("box", "offered") in stored and ("deal_document", "accepted") in stored
    assert not any(s.implemented for s in b.solutions)
    approved = next(s for s in b.solutions if s.kind == "document" and s.stored_state == "approved")
    assert approved.reviewer_approved and approved.implementation_status == "reviewer_approved"
    assert approved.problem_refs == ("P1",)
    assert "Delivered" not in cm.implementation_summary(b)

    # (d) files: metadata only
    assert [f.name for f in b.files] == ["menu.pdf"] and b.files[0].text_available is False

    # (e) tried, rejected (stored + derived), decisions
    assert any(t.what == "WhatsApp groups" and not t.derived for t in b.tried)
    assert any(t.derived for t in b.tried)
    refs = {(r.derived, r.text) for r in b.rejections}
    assert (False, "Send reminders") in refs and (True, "mujhe yeh nahi chahiye") in refs
    kinds = {(d.kind, d.status) for d in b.decisions}
    assert ("approval", "pending") in kinds and ("approval", "approved") in kinds
    assert ("offer", "blocked") in kinds and ("document", "approved") in kinds

    # (f) facts keep owner-said apart from guesses; profile and memory are not owner-said
    by = {(f.key, f.status): f.value for f in b.facts}
    assert by[("budget", "owner_said")] == "50k" and by[("cause", "pi_inferred")] == "supplier late"
    assert by[("staff_count", "confirmed")] == "4" and ("website", "page_read") in by
    assert by[("location", "remembered")] == "Lahore"
    a = cm.answered_from_records("budget", b)
    assert a.value == "50k" and a.problem_ref == "P1" and a.owner_confirmed
    assert cm.answered_from_records("location", b).value in ("Lahore shop", "Lahore")
    assert cm.answered_from_records("cause", b).value == "no tracking"  # P2's guess never wins

    # correction history: current value, every prior value, the correcting message
    budget = next(c for c in b.corrections if c.field == "constraints.budget")
    assert budget.current["text"] == "50k"
    assert [p.value["text"] for p in budget.prior] == ["30k"] and budget.prior[0].msg == "m2"
    title = next(c for c in b.corrections if c.field == "title")
    assert title.prior[0].value == "Orders lost" and title.current == "Orders get lost"

    # nothing from workspace B anywhere
    assert "B-SECRET" not in str(b.to_dict())
    assert "B-SECRET" not in str(b.known_records())
    again = await cm.build_context(db, w.scope_a, customer_id=w.cust_a, conversation_id=w.conv_a.id)
    assert again.to_dict() == b.to_dict()  # deterministic

    recs = b.known_records()
    assert {r["tenant_id"] for r in recs} == {str(w.scope_a.tenant_id)}
    await w.a.close()
    await w.b.close()


async def test_nothing_leaks_between_workspaces_or_customers(api, business_db, monkeypatch):
    db = business_db
    w = await two_chats(api, db, monkeypatch)
    if not set(NEW) <= await present_columns(db):
        await migrate(db, "upgrade")
    await seed_a(db, w)
    await seed_b(db, w)
    # a second customer inside workspace A
    await w.a.process("A2-SECRET hello", "iso-a2", sender="15550000009")
    other = await db.scalar(
        select(PiConversation).where(
            PiConversation.tenant_id == w.scope_a.tenant_id,
            PiConversation.id != w.conv_a.id,
            PiConversation.contact_wa_id == "15550000009",
        )
    )
    assert other is not None and other.customer_id != w.cust_a
    for scope, cust, banned in (
        (w.scope_b, w.cust_b, "50k"),
        (w.scope_a, other.customer_id, "50k"),
    ):
        got = await cm.build_context(db, scope, customer_id=cust)
        assert banned not in str(got.to_dict()) and "menu.pdf" not in str(got.to_dict())
        assert not got.solutions and (scope is w.scope_b or not got.problems)
    # wrong-scope reads find nothing
    assert (await cm.build_context(db, w.scope_a, customer_id=w.cust_b)).empty
    assert (await cm.build_context(db, w.scope_b, customer_id=w.cust_a)).empty
    # a conversation of another workspace or customer with the right customer id: nothing
    foreign = await cm.build_context(
        db, w.scope_a, customer_id=w.cust_a, conversation_id=w.conv_b.id
    )
    assert foreign.empty and not foreign.messages
    wrong_customer = await cm.build_context(
        db, w.scope_a, customer_id=w.cust_a, conversation_id=other.id
    )
    assert wrong_customer.empty
    assert "A2-SECRET" not in str(
        (await cm.build_context(db, w.scope_a, customer_id=w.cust_a)).to_dict()
    )
    await w.a.close()
    await w.b.close()


async def test_an_erased_customer_returns_an_empty_bundle(api, business_db, monkeypatch):
    db = business_db
    w = await two_chats(api, db, monkeypatch)
    if not set(NEW) <= await present_columns(db):
        await migrate(db, "upgrade")
    await seed_a(db, w)
    await seed_b(db, w)
    before = await cm.build_context(db, w.scope_a, customer_id=w.cust_a)
    assert not before.empty
    await brain_erase.erase_customer(db, w.scope_a, w.cust_a)
    after = await cm.build_context(db, w.scope_a, customer_id=w.cust_a, conversation_id=w.conv_a.id)
    assert after.erased and after.empty and not after.solutions  # documents are kept but not served
    assert cm.answered_from_records("budget", after) is None
    assert cm.what_is_already_known(after) == "" and cm.implementation_summary(after) == ""
    # the other workspace is untouched
    other = await cm.build_context(db, w.scope_b, customer_id=w.cust_b)
    assert not other.erased and other.messages and other.problems
    await w.a.close()
    await w.b.close()


async def test_requirements_are_unavailable_not_empty_before_migration_0053(
    api, business_db, monkeypatch
):
    db = business_db
    w = await two_chats(api, db, monkeypatch)
    if set(NEW) <= await present_columns(db):
        await migrate(db, "downgrade")
    assert not set(NEW) & await present_columns(db)
    first = problem(w.scope_a, w.cust_a, 1, "Orders get lost")
    db.add(first)
    await db.flush()
    b = await cm.build_context(db, w.scope_a, customer_id=w.cust_a)
    assert b.requirements_available is False
    assert "unavailable: requirements" in b.unavailable
    assert [p.title for p in b.problems] == ["Orders get lost"]  # the rest still returns
    assert b.problems[0].budget is None and b.problems[0].tried == ()
    # the transaction is still usable afterwards
    assert await db.scalar(text("SELECT 1")) == 1
    await w.a.close()
    await w.b.close()


async def test_a_failing_sub_query_is_recorded_and_the_rest_returns(api, business_db, monkeypatch):
    db = business_db
    w = await two_chats(api, db, monkeypatch)
    if not set(NEW) <= await present_columns(db):
        await migrate(db, "upgrade")
    await seed_a(db, w)

    async def broken(*args, **kwargs):
        await db.execute(text("SELECT * FROM table_that_does_not_exist"))

    monkeypatch.setattr(cm, "_files", broken)
    b = await cm.build_context(db, w.scope_a, customer_id=w.cust_a)
    assert "unavailable: files" in b.unavailable and not b.files
    assert b.problems and b.solutions and b.messages  # everything else still returned
    assert await db.scalar(text("SELECT 1")) == 1

    async def exploding(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cm, "_build", exploding)
    last = await cm.build_context(db, w.scope_a, customer_id=w.cust_a)
    assert last.unavailable == ("unavailable: context",) and last.empty
    await w.a.close()
    await w.b.close()


async def test_caps_set_truncated_flags(api, business_db, monkeypatch):
    db = business_db
    w = await two_chats(api, db, monkeypatch)
    if not set(NEW) <= await present_columns(db):
        await migrate(db, "upgrade")
    await seed_a(db, w)
    tiny = Limits(
        messages=1,
        previous_conversations=0,
        problems=1,
        solutions=2,
        files=1,
        rejections=1,
        decisions=1,
        facts=2,
        corrections=1,
        chars_per_text=10,
    )
    b = await cm.build_context(
        db, w.scope_a, customer_id=w.cust_a, conversation_id=w.conv_a.id, limits=tiny
    )
    assert len(b.messages) == 1 and len(b.messages[0].text) <= 10
    assert (
        len(b.problems) == 1
        and len(b.solutions) == 2
        and len(b.decisions) == 1
        and len(b.facts) == 2
    )
    assert {
        "messages",
        "previous_conversations",
        "problems",
        "solutions",
        "decisions",
        "facts",
    } <= set(b.truncated)
    small = Limits(total_chars=40)
    c = await cm.build_context(
        db, w.scope_a, customer_id=w.cust_a, conversation_id=w.conv_a.id, limits=small
    )
    assert sum(len(m.text) for m in c.messages) <= 40 and "messages" in c.truncated
    await w.a.close()
    await w.b.close()
