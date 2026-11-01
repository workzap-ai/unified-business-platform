"""The memory ledgers on a real database (migration 0056): decisions with supersession, rejections
read by the idea filter, document texts, the staff-only delivered marker, tenant isolation, the
single reader (`build_context`), the customer export and the erase. Brain mode only; with empty
tables the bundle is as before."""

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from test_pi_pipeline import pi_workspace

from app.modules.customers.files import save as save_file
from app.modules.pi import (
    brain_erase,
    context_memory,
    delivery_marker,
    document_texts,
    idea_filter,
    memory_answer,
    memory_ledger,
    solution_ideas,
)
from app.modules.pi.brain_docs_models import PiBrainDocument
from app.modules.pi.memory_models import PiDecision, PiDocumentText, PiRejection
from app.modules.pi.models import PiMessage
from app.modules.pi.solution_models import PiIdeaArm, PiSolutionMemory
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

pytestmark = pytest.mark.integration
BRAIN = {"pi_mode": "brain"}


async def workspace(api, db, number):
    pi = await pi_workspace(api, db, number=number)
    await pi.process("My shop stock keeps running out", f"led-{number}")
    conversation = await pi.conversation()
    scope = WorkspaceScope.system(
        conversation.tenant_id, conversation.environment_id, frozenset(), "test"
    )
    message = await db.scalar(
        select(PiMessage).where(
            PiMessage.conversation_id == conversation.id, PiMessage.direction == "inbound"
        )
    )
    return pi, conversation, scope, message


async def rows(db, model, scope, customer_id):
    return list(
        await db.scalars(
            select(model)
            .where(
                model.tenant_id == scope.tenant_id,
                model.environment_id == scope.environment_id,
                model.customer_id == customer_id,
            )
            .execution_options(populate_existing=True)
        )
    )


def decision(kind="yes", effects=None, brief=None):
    return SimpleNamespace(brief=brief or {}, effects=effects or [])


# --------------------------------------------------------------------------- decisions
async def test_a_decision_is_written_once_and_a_replay_does_nothing(api, business_db):
    pi, conv, scope, message = await workspace(api, business_db, "111111111")
    args = dict(
        customer_id=conv.customer_id,
        kind="yes",
        subject_ref=memory_ledger.OFFER_SUBJECT,
        owner_words="yes please, call 0311 2546598",
        source_message_id=message.id,
    )
    first = await memory_ledger.record_decision(business_db, scope, **args)
    again = await memory_ledger.record_decision(business_db, scope, **args)
    assert first is not None and again is not None and again.id == first.id
    stored = await rows(business_db, PiDecision, scope, conv.customer_id)
    assert len(stored) == 1 and stored[0].status == "active"
    assert "2546598" not in stored[0].owner_words and stored[0].actor == "owner"
    await pi.close()


async def test_a_newer_statement_supersedes_the_older_and_keeps_it(api, business_db):
    pi, conv, scope, message = await workspace(api, business_db, "222222222")
    cid = conv.customer_id
    yes = await memory_ledger.record_decision(
        business_db,
        scope,
        customer_id=cid,
        kind="yes",
        subject_ref=memory_ledger.OFFER_SUBJECT,
        owner_words="yes",
        source_message_id=message.id,
    )
    no = await memory_ledger.record_decision(
        business_db,
        scope,
        customer_id=cid,
        kind="decline",
        subject_ref=memory_ledger.OFFER_SUBJECT,
        owner_words="no, not now",
        source_message_id=uuid4(),
    )
    assert yes is not None and no is not None
    stored = {d.kind: d for d in await rows(business_db, PiDecision, scope, cid)}
    assert set(stored) == {"yes", "decline"}  # the old row is kept, never overwritten
    assert stored["yes"].status == "superseded" and stored["yes"].valid_to is not None
    assert stored["yes"].owner_words == "yes"
    assert stored["decline"].status == "active" and stored["decline"].supersedes_id == yes.id
    # an owner withdrawal keeps the row too
    assert await memory_ledger.withdraw_decision(
        business_db, scope, customer_id=cid, subject_ref=memory_ledger.OFFER_SUBJECT
    )
    await business_db.refresh(no)
    assert no.status == "withdrawn"
    await pi.close()


async def test_the_same_statement_again_without_a_message_changes_nothing(api, business_db):
    pi, conv, scope, _ = await workspace(api, business_db, "333333333")
    for _ in range(3):
        await memory_ledger.record_decision(
            business_db,
            scope,
            customer_id=conv.customer_id,
            kind="document_approval",
            subject_ref="doc:SD-0001",
            actor="staff",
        )
    assert len(await rows(business_db, PiDecision, scope, conv.customer_id)) == 1
    await pi.close()


async def test_the_gate_hook_writes_the_decisions_and_only_in_brain_mode(api, business_db):
    pi, conv, scope, _ = await workspace(api, business_db, "444444444")
    cid = conv.customer_id
    await memory_ledger.on_decision(
        business_db, scope, conv, decision(effects=["request_solution"]), {"pi_mode": "standard"}
    )
    assert await rows(business_db, PiDecision, scope, cid) == []  # other workspaces: unchanged
    await memory_ledger.on_decision(
        business_db, scope, conv, decision(brief={"offer_asked": True}), BRAIN
    )
    await memory_ledger.on_decision(
        business_db, scope, conv, decision(effects=["request_solution"]), BRAIN
    )
    await memory_ledger.on_decision(
        business_db, scope, conv, decision(brief={"offer_declined": True}), BRAIN
    )
    kinds = {d.kind: d for d in await rows(business_db, PiDecision, scope, cid)}
    assert set(kinds) == {"offer", "yes", "decline"}
    assert kinds["offer"].actor == "pi" and kinds["offer"].status == "superseded"
    assert kinds["yes"].source_message_id is not None  # the owner's own message
    assert kinds["decline"].status == "active"
    refused = await rows(business_db, PiRejection, scope, cid)
    assert [r.target_kind for r in refused] == ["offer"]
    # a later yes takes the offer rejection back (row kept)
    await memory_ledger.on_decision(
        business_db, scope, conv, decision(effects=["request_solution"]), BRAIN
    )
    assert [r.status for r in await rows(business_db, PiRejection, scope, cid)] == ["reversed"]
    await pi.close()


async def test_a_document_approval_is_a_staff_decision(api, business_db):
    pi, conv, scope, _ = await workspace(api, business_db, "555555555")
    doc = SimpleNamespace(customer_id=conv.customer_id, ref="Q-0001")
    await memory_ledger.on_document_approved(business_db, scope, doc, BRAIN)
    (row,) = await rows(business_db, PiDecision, scope, conv.customer_id)
    assert row.kind == "document_approval" and row.actor == "staff"
    assert row.subject_ref == "doc:Q-0001"
    await pi.close()


# --------------------------------------------------------------------------- rejections
async def idea(db, scope, customer_id, text):
    arm = PiIdeaArm(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        arm_key=f"retail:stock:{uuid4().hex[:6]}",
        industry_key="retail",
        problem_id="stock",
        text=text,
    )
    db.add(arm)
    await db.flush()
    return arm


async def test_a_rejected_idea_is_stored_and_the_idea_filter_will_not_offer_it_again(
    api, business_db
):
    pi, conv, scope, message = await workspace(api, business_db, "666666666")
    cid = conv.customer_id
    put = await api.patch("/api/v1/pi/settings/response_rules", json={"value": BRAIN})
    assert put.status_code == 200, put.text
    text = "Offer a small discount to your regular customers every month"
    arm = await idea(business_db, scope, cid, text)
    business_db.add(
        PiSolutionMemory(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            customer_id=cid,
            idea_arm_id=arm.id,
            industry_key="retail",
            problem_id="stock",
            given_at=message.created_at,
        )
    )
    await business_db.flush()
    from app.modules.pi import solution_score

    reaction = solution_score.classify("we are already doing that")
    assert reaction is not None
    await solution_ideas.react(
        business_db,
        scope,
        customer_id=cid,
        arms=[arm],
        reaction=reaction,
        message_id=message.id,
    )
    (rejection,) = await rows(business_db, PiRejection, scope, cid)
    assert rejection.target_kind == "idea" and rejection.status == "active"
    assert rejection.idea_text == text and rejection.idea_hash == memory_ledger.idea_hash(text)
    assert rejection.source_message_id == message.id and rejection.owner_words
    assert await memory_ledger.rejected_ideas(business_db, scope, cid) == [text]
    ctx = idea_filter.with_rejections(
        None, await memory_ledger.rejected_ideas(business_db, scope, cid)
    )
    assert "G7" in idea_filter.failures(text, "slow sales", ctx)
    # the bundle (single reader) shows it with its source and status
    bundle = await context_memory.build_context(business_db, scope, customer_id=cid)
    stored = [r for r in bundle.rejections if r.ref.startswith("rej:")]
    assert stored and stored[0].status == "active" and stored[0].source == f"msg:{message.id}"
    # taking it back: the row stays, the filter no longer blocks
    assert (
        await memory_ledger.reverse_rejections(
            business_db, scope, customer_id=cid, target_kind="idea", target_key=arm.arm_key
        )
        == 1
    )
    assert await memory_ledger.rejected_ideas(business_db, scope, cid) == []
    assert len(await rows(business_db, PiRejection, scope, cid)) == 1
    await pi.close()


async def test_rejecting_the_same_idea_twice_keeps_one_active_row(api, business_db):
    pi, conv, scope, _ = await workspace(api, business_db, "777777777")
    for _ in range(2):
        await memory_ledger.record_rejection(
            business_db,
            scope,
            customer_id=conv.customer_id,
            target_kind="idea",
            target_key="retail:stock:q1",
            idea_text="Count the shelf every evening",
        )
    assert len(await rows(business_db, PiRejection, scope, conv.customer_id)) == 1
    await pi.close()


# --------------------------------------------------------------------------- document texts
async def test_document_text_is_stored_once_with_references_and_read_back(api, business_db):
    pi, conv, scope, _ = await workspace(api, business_db, "888888888")
    cid = conv.customer_id
    raw = ("Payment is due within 14 days. Call 0311 2546598 for questions. " * 150).encode()
    saved = await save_file(business_db, scope, cid, raw, "terms.txt", "upload")
    added = await document_texts.store(
        business_db, scope, customer_id=cid, file_id=saved.id, raw=raw
    )
    assert added >= 2
    assert (
        await document_texts.store(business_db, scope, customer_id=cid, file_id=saved.id, raw=raw)
        == 0
    )
    stored = await rows(business_db, PiDocumentText, scope, cid)
    assert len(stored) == added and stored[0].ref == "section 1"
    assert all("2546598" not in r.text for r in stored)
    bundle = await context_memory.build_context(business_db, scope, customer_id=cid)
    (file_item,) = [f for f in bundle.files if f.id == saved.id]
    assert file_item.text_available and file_item.text_refs[0] == "section 1"
    # the hook stores nothing outside brain mode
    other = await save_file(business_db, scope, cid, raw + b"x", "other.txt", "upload")
    assert (
        await document_texts.on_file_saved(
            business_db,
            scope,
            customer_id=cid,
            file_id=other.id,
            raw=raw,
            response_rules={"pi_mode": "standard"},
        )
        == 0
    )
    await pi.close()


# --------------------------------------------------------------------------- delivered marker
async def brain_doc(db, scope, customer_id, status):
    doc = PiBrainDocument(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        customer_id=customer_id,
        offer_id=uuid4(),
        kind="quote",
        number=int(uuid4().int % 9000) + 1,
        status=status,
    )
    db.add(doc)
    await db.flush()
    return doc


async def test_delivered_and_verified_are_set_only_through_the_staff_path(api, business_db):
    pi, conv, scope, _ = await workspace(api, business_db, "999999990")
    cid = conv.customer_id
    staff = uuid4()
    draft = await brain_doc(business_db, scope, cid, "draft")
    with pytest.raises(BusinessRuleViolation):
        await delivery_marker.mark_delivered(business_db, scope, draft.id, staff)  # not approved
    doc = await brain_doc(business_db, scope, cid, "approved")
    with pytest.raises(BusinessRuleViolation):
        await delivery_marker.mark_delivered(business_db, scope, doc.id, None)  # no staff member
    with pytest.raises(BusinessRuleViolation):
        await delivery_marker.mark_verified(business_db, scope, doc.id, staff)  # not delivered yet
    # nothing in the chat path has set it: the bundle does not call it delivered
    bundle = await context_memory.build_context(business_db, scope, customer_id=cid)
    assert not any(s.delivered_at or s.implemented for s in bundle.solutions if s.kind == "quote")
    stamp = await delivery_marker.mark_delivered(business_db, scope, doc.id, staff)
    assert await delivery_marker.mark_delivered(business_db, scope, doc.id, staff) == stamp
    await delivery_marker.mark_verified(business_db, scope, doc.id, staff)
    seen = await business_db.execute(
        select(
            PiBrainDocument.delivered_at, PiBrainDocument.verified_at, PiBrainDocument.verified_by
        ).where(PiBrainDocument.id == doc.id)
    )
    delivered, verified, by = seen.one()
    assert delivered is not None and verified is not None and by == staff
    bundle = await context_memory.build_context(business_db, scope, customer_id=cid)
    marked = [s for s in bundle.solutions if s.delivered_at]
    assert len(marked) == 1 and marked[0].implemented and marked[0].verified_at
    await pi.close()


# --------------------------------------------------------------------------- empty = unchanged
async def test_empty_tables_leave_the_bundle_as_it_was(api, business_db):
    pi, conv, scope, _ = await workspace(api, business_db, "999999991")
    bundle = await context_memory.build_context(
        business_db, scope, customer_id=conv.customer_id, conversation_id=conv.id
    )
    assert not any(u for u in bundle.unavailable)
    assert not [d for d in bundle.decisions if d.actor]  # no ledger decisions
    assert not [r for r in bundle.rejections if r.ref.startswith("rej:")]
    assert all(not f.text_refs for f in bundle.files)
    assert all(not s.delivered_at for s in bundle.solutions)
    await pi.close()


# --------------------------------------------------------------------------- two tenants
async def test_two_tenants_never_see_each_others_ledgers(api, business_db):
    pi_a, conv_a, scope_a, msg_a = await workspace(api, business_db, "999999992")
    pi_b, conv_b, scope_b, _ = await workspace(api, business_db, "999999993")
    assert scope_a.tenant_id != scope_b.tenant_id
    await memory_ledger.record_decision(
        business_db,
        scope_a,
        customer_id=conv_a.customer_id,
        kind="yes",
        subject_ref=memory_ledger.OFFER_SUBJECT,
        owner_words="secret-of-a",
        source_message_id=msg_a.id,
    )
    await memory_ledger.record_rejection(
        business_db,
        scope_a,
        customer_id=conv_a.customer_id,
        target_kind="idea",
        target_key="a:key",
        idea_text="secret idea of a",
    )
    # B reading A's customer id, and A reading with B's scope, see nothing
    for scope, cid in ((scope_b, conv_a.customer_id), (scope_a, conv_b.customer_id)):
        bundle = await context_memory.build_context(business_db, scope, customer_id=cid)
        assert not [d for d in bundle.decisions if d.actor]
        assert not [r for r in bundle.rejections if r.ref.startswith("rej:")]
        assert await memory_ledger.rejected_ideas(business_db, scope, cid) == []
    # a row cannot be written across tenants: the composite key refuses a foreign customer
    with pytest.raises(IntegrityError):
        async with business_db.begin_nested():
            business_db.add(
                PiDecision(
                    tenant_id=scope_b.tenant_id,
                    environment_id=scope_b.environment_id,
                    customer_id=conv_a.customer_id,
                    kind="yes",
                    subject_ref="x",
                )
            )
            await business_db.flush()
    # erasing B's customer leaves A's rows alone
    await brain_erase.erase_customer(business_db, scope_b, conv_b.customer_id)
    assert len(await rows(business_db, PiDecision, scope_a, conv_a.customer_id)) == 1
    assert len(await rows(business_db, PiRejection, scope_a, conv_a.customer_id)) == 1
    await pi_a.close()
    await pi_b.close()


# --------------------------------------------------------------------------- erase and export
async def test_erase_covers_every_new_table(api, business_db):
    pi, conv, scope, message = await workspace(api, business_db, "999999994")
    cid = conv.customer_id
    await memory_ledger.record_decision(
        business_db,
        scope,
        customer_id=cid,
        kind="yes",
        subject_ref=memory_ledger.OFFER_SUBJECT,
        owner_words="yes",
        source_message_id=message.id,
    )
    await memory_ledger.record_decision(
        business_db,
        scope,
        customer_id=cid,
        kind="decline",
        subject_ref=memory_ledger.OFFER_SUBJECT,
        owner_words="no",
        source_message_id=uuid4(),
    )
    await memory_ledger.record_rejection(
        business_db, scope, customer_id=cid, target_kind="offer", target_key="box:offer"
    )
    raw = ("Delivery within two weeks of payment. " * 150).encode()
    saved = await save_file(business_db, scope, cid, raw, "scope.txt", "upload")
    await document_texts.store(business_db, scope, customer_id=cid, file_id=saved.id, raw=raw)
    texts = len(await rows(business_db, PiDocumentText, scope, cid))
    assert texts >= 1

    result = await brain_erase.erase_customer(business_db, scope, cid)
    removed = result["removed"]
    assert removed["decisions"] == 2 and removed["rejections"] == 1
    assert removed["document_texts"] == texts
    assert result["complete"] and not result["skipped"]
    for model in (PiDecision, PiRejection, PiDocumentText):
        assert await rows(business_db, model, scope, cid) == []
    bundle = await context_memory.build_context(business_db, scope, customer_id=cid)
    assert bundle.erased or not [d for d in bundle.decisions if d.actor]
    await pi.close()


async def test_the_customer_export_includes_the_new_data(api, business_db):
    pi, conv, scope, message = await workspace(api, business_db, "999999995")
    cid = conv.customer_id
    await memory_ledger.record_decision(
        business_db,
        scope,
        customer_id=cid,
        kind="yes",
        subject_ref=memory_ledger.OFFER_SUBJECT,
        owner_words="yes please",
        source_message_id=message.id,
    )
    await memory_ledger.record_rejection(
        business_db,
        scope,
        customer_id=cid,
        target_kind="idea",
        target_key="r:1",
        idea_text="Hand out flyers on Fridays",
        source_message_id=message.id,
    )
    raw = ("Warranty lasts twelve months from delivery. " * 150).encode()
    saved = await save_file(business_db, scope, cid, raw, "warranty.txt", "upload")
    await document_texts.store(business_db, scope, customer_id=cid, file_id=saved.id, raw=raw)
    response = await api.get(f"/api/v1/pi/customers/{cid}/export")
    assert response.status_code == 200, response.text
    memory = response.json()["pi_memory"]
    (yes,) = [d for d in memory["decisions"] if d.get("actor")]
    assert (
        yes["kind"] == "yes" and yes["status"] == "active" and yes["source"] == f"msg:{message.id}"
    )
    (no,) = [r for r in memory["rejections"] if r["ref"].startswith("rej:")]
    assert no["text"] == "Hand out flyers on Fridays" and no["status"] == "active"
    assert memory["document_texts"] and memory["document_texts"][0]["ref"] == "section 1"
    assert any(f["text_refs"] for f in memory["files"])
    # the chat answer lists the same records with their status
    bundle = await context_memory.build_context(business_db, scope, customer_id=cid)
    text = memory_answer.reply(context_memory.known_records(bundle), "en", "nothing")
    assert "yes please" in text and "Hand out flyers" in text and "status: active" in text
    await pi.close()


async def test_counts_in_the_new_tables_are_zero_for_a_fresh_workspace(api, business_db):
    pi, conv, scope, _ = await workspace(api, business_db, "999999996")
    for model in (PiDecision, PiRejection, PiDocumentText):
        n = await business_db.scalar(
            select(func.count()).select_from(model).where(model.tenant_id == scope.tenant_id)
        )
        assert n == 0
    await pi.close()


# --------------------------------------------------------------------------- scope and price
async def test_an_approved_scope_and_price_are_decisions_that_supersede_the_last(api, business_db):
    pi, conv, scope, _ = await workspace(api, business_db, "577777777")
    cid = conv.customer_id
    staff = uuid4()

    def quote(version, total, included):
        return SimpleNamespace(
            customer_id=cid,
            ref="Q-0001" if version == 1 else f"Q-0001-v{version}",
            version=version,
            kind="quote",
            total=total,
            currency="PKR",
            approved_by=staff,
            content={"included": included},
        )

    await memory_ledger.on_document_approved(
        business_db, scope, quote(1, Decimal("15000.00"), ["stock sheet", "reorder alerts"]), BRAIN
    )
    await memory_ledger.on_document_approved(
        business_db, scope, quote(2, Decimal("1250000.50"), ["stock sheet"]), BRAIN
    )
    # the same approval again changes nothing
    await memory_ledger.on_document_approved(
        business_db, scope, quote(2, Decimal("1250000.50"), ["stock sheet"]), BRAIN
    )
    every = await rows(business_db, PiDecision, scope, cid)
    for subject in ("scope", "price"):
        mine = [r for r in every if r.subject_ref == subject]
        live = [r for r in mine if r.status == "active"]
        assert len(mine) == 2 and len(live) == 1
        assert live[0].actor == "staff" and live[0].supersedes_id is not None
        (old,) = [r for r in mine if r.status == "superseded"]
        assert old.valid_to is not None and live[0].supersedes_id == old.id
    price = next(r for r in every if r.subject_ref == "price" and r.status == "active")
    assert price.owner_words.startswith("1250000.50 PKR (Q-0001-v2, version 2")
    assert str(staff) in price.owner_words
    # the single reader shows both, newest first, with their original wording
    bundle = await context_memory.build_context(business_db, scope, customer_id=cid)
    shown = {d.kind: d for d in bundle.decisions if d.status == "active"}
    assert "stock sheet" in shown["scope"].text and "1250000.50" in shown["price"].text
    # a draft (no total) records no price, and other workspaces record nothing
    await memory_ledger.on_document_approved(
        business_db, scope, quote(3, None, ["stock sheet"]), {"pi_mode": "standard"}
    )
    assert len(await rows(business_db, PiDecision, scope, cid)) == len(every)


# --------------------------------------------------------------------------- scanned and staff
async def test_scanned_pages_and_a_staff_upload_are_stored_scoped_and_erased(api, business_db):
    pi, conv, scope, _ = await workspace(api, business_db, "999999993")
    cid = conv.customer_id
    scan = await save_file(business_db, scope, cid, b"%PDF-1.4 scan", "scan.pdf", "whatsapp")
    added = await document_texts.store_scanned(
        business_db,
        scope,
        customer_id=cid,
        file_id=scan.id,
        pages=[(1, "Invoice for Ali, call 0311 2546598"), (3, "Total due 900")],
        total=7,
    )
    assert added == 3
    stored = await rows(business_db, PiDocumentText, scope, cid)
    refs = sorted(r.ref for r in stored)
    assert refs == [
        "page 1 (read from a picture)",
        "page 3 (read from a picture)",
        "pages not read",
    ]
    assert all("2546598" not in r.text for r in stored)

    raw = ("Staff note: the delivery is Monday. " * 120).encode()
    staff = await save_file(business_db, scope, cid, raw, "plan.txt", "upload")
    assert (
        await document_texts.store_staff_file(
            business_db,
            scope,
            customer_id=cid,
            file_id=staff.id,
            raw=raw,
            response_rules={"pi_mode": "standard"},
        )
        == 0
    )
    n = await document_texts.store_staff_file(
        business_db, scope, customer_id=cid, file_id=staff.id, raw=raw, response_rules=BRAIN
    )
    assert n >= 1
    junk = await save_file(business_db, scope, cid, b"%PDF-1.4 broken", "x.pdf", "upload")
    assert (
        await document_texts.store_staff_file(
            business_db,
            scope,
            customer_id=cid,
            file_id=junk.id,
            raw=b"%PDF-1.4 broken",
            response_rules=BRAIN,
        )
        == 0
    )
    bundle = await context_memory.build_context(business_db, scope, customer_id=cid)
    assert [f for f in bundle.files if f.id == staff.id][0].text_available
    removed = (await brain_erase.erase_customer(business_db, scope, cid))["removed"]
    assert removed["document_texts"] == added + n
    assert await rows(business_db, PiDocumentText, scope, cid) == []
    await pi.close()
