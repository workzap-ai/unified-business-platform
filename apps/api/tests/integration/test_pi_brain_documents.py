"""Brain mode: the yes becomes a drafted solution document and quote, a reviewer prices and approves
them, pi sends two PDFs and the decision buttons, and the person decides. Real database/webhook/
worker; the AI and WhatsApp are mocked."""

import json
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
from sqlalchemy import select
from test_pi_brain_problems import create, say, workspace
from test_pi_customer_payments import MEEZAN
from test_pi_deals import _public
from test_pi_service_conversations import turn

from app.ai.manager import LLMManager
from app.modules.pi import decisions
from app.modules.pi.brain_docs import Component, SolutionDraft, WontDo
from app.modules.pi.brain_docs_models import PiBrainDocument
from app.modules.pi_saas.jobs import draft_brain_documents
from app.modules.pi_saas.models import PiStaffRequest

pytestmark = pytest.mark.integration

DOCS = "/api/v1/pi/brain-documents"


@pytest.fixture(autouse=True)
def roomy_limits(monkeypatch):
    """A whole journey (offer, approval, payment) is more than eight messages a minute."""
    from datetime import timedelta

    from app.modules.pi import guard

    for name in ("CONVERSATION_BURST", "AI_REPLY_LOOP"):
        current = getattr(guard, name)
        monkeypatch.setattr(guard, name, guard.Limit(current.code, 500, timedelta(minutes=1)))


OPENING = "Hi, I'm pi, an AI from Workzap."


def chat_model(context, n):
    said = context["latest_customer_message"]
    ops, refs, changes = [], [], []
    reply = "Noted. Anything else getting in the way?"
    if "Best-sellers" in said:
        ops = [
            create("Best-sellers run out in two shops", "Best-sellers run out."),
            create("Cashiers late on weekends", "Cashiers come late.", "people_staff"),
        ]
        reply = f"{OPENING} Noted both. Anything else getting in the way?"
    elif "only 2 shops" in said:
        changes = ["Cover 2 shops instead of 3"]
        reply = "Understood."
    return turn(
        reply=reply, language="en", problem_ops=ops, include_refs=refs, change_requests=changes
    )


def solution_for(payload, **changes):
    """What the drafter model returns: one component per problem, and a plain wont_do."""
    refs = [p["ref"] for p in payload["problems"]]
    base = dict(
        components=[
            Component(text="A simple check would help with this problem.", problems=[ref])
            for ref in refs
        ],
        covers=["Your shops and the people who run them"],
        wont_do=[WontDo(text="It would not change how you order from your suppliers.")],
        needs=["One contact person in each shop"],
    )
    return SolutionDraft(**{**base, **changes})


def install_models(monkeypatch, draft=solution_for):
    """Chat turns come from chat_model, the document drafter from `draft`; both are recorded."""
    seen = {"chat": 0, "drafts": [], "prompts": []}

    async def complete(self, scope, output, **kwargs):
        messages = kwargs["messages"]
        if output is SolutionDraft:
            payload = json.loads(messages[1].text())
            seen["drafts"].append(payload)
            value = draft(payload)
        else:
            text = messages[-1].text()
            seen["prompts"].append(text)
            if text.startswith("{"):
                seen["chat"] += 1
                seen["last"] = chat_model(json.loads(text), seen["chat"])
            value = seen["last"]
        return SimpleNamespace(value=value, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)
    return seen


async def accepted_offer(api, db, monkeypatch, **models):
    """Summary, offer and a yes: the chat is in S6 and the drafting job is due."""
    seen = install_models(monkeypatch, **models)
    pi = await workspace(api, db)
    await say(pi, "Best-sellers run out and cashiers are late on weekends", "dc-1")
    await say(pi, "That's all", "dc-2")
    await say(pi, "looks right", "dc-3")
    await say(pi, "yes", "dc-4")
    await say(pi, "all of them", "dc-5")
    conversation = await pi.conversation()
    await db.refresh(conversation)
    assert conversation.flow_state == "S6_PREPARING"
    return pi, seen, conversation


async def drafted(pi, db, conversation):
    await draft_brain_documents(pi.ctx, str(conversation.id))
    rows = (await db.scalars(select(PiBrainDocument).order_by(PiBrainDocument.kind.desc()))).all()
    return {r.kind: r for r in rows}


async def bank(api):
    put = await api.put(
        "/api/v1/pi/customer-payments/settings",
        json={"bank_enabled": True, "bank_accounts": [MEEZAN]},
    )
    assert put.status_code == 200, put.text


async def price(api, quote_id, total="450000"):
    patch = await api.patch(
        f"{DOCS}/{quote_id}",
        json={
            "cost": {"total": total, "currency": "PKR", "tax_text": "Tax as applicable"},
            "time": {
                "estimate": "About six weeks from kickoff",
                "milestones": ["Week 2: first check"],
            },
            "valid_until": "2030-12-31",
        },
    )
    assert patch.status_code == 200, patch.text
    return patch.json()


async def approve_both(api, docs):
    await bank(api)
    await price(api, docs["quote"].id)
    for kind in ("solution", "quote"):
        done = await api.post(f"{DOCS}/{docs[kind].id}/approve")
        assert done.status_code == 200, done.text
        assert done.json()["status"] == "approved"


def sent_of(pi, kind):
    return [m for m in pi.sent if m.get("type") == kind]


async def test_yes_drafts_a_solution_document_and_a_quote_for_review(api, business_db, monkeypatch):
    pi, seen, conversation = await accepted_offer(api, business_db, monkeypatch)
    assert conversation.service_brief["offer"].get("offer_id") is None
    docs = await drafted(pi, business_db, conversation)
    solution, quote = docs["solution"], docs["quote"]
    assert (solution.ref, quote.ref) == ("SD-0001", "Q-0001")
    assert solution.status == quote.status == "in_review"
    assert solution.drafted_by == "pi" and solution.offer_id == quote.offer_id
    assert quote.solution_id == solution.id
    # Section 1 is the person's own words; nothing is priced.
    titles = {p["title"] for p in solution.content["problems"]}
    assert titles == {"Best-sellers run out in two shops", "Cashiers late on weekends"}
    assert {q for p in solution.content["problems"] for q in p["quotes"]} == {
        "Best-sellers run out.",
        "Cashiers come late.",
    }
    assert len(solution.content["components"]) == 2 and solution.content["wont_do"]
    assert quote.total is None and quote.content["cost"]["total"] is None
    assert quote.content["included"] == [c["text"] for c in solution.content["components"]]
    assert len(seen["drafts"]) == 1  # the first draft already followed the rules
    # The person has been sent nothing; the team is asked to review.
    assert sent_of(pi, "document") == []
    await business_db.refresh(conversation)
    assert conversation.service_brief["offer"]["offer_id"] == str(solution.offer_id)
    request = (
        await business_db.scalars(
            select(PiStaffRequest).where(PiStaffRequest.kind == "review_document")
        )
    ).one()
    assert "SD-0001" in request.question and "Q-0001" in request.question
    # A second run does not draft again.
    await draft_brain_documents(pi.ctx, str(conversation.id))
    assert len((await business_db.scalars(select(PiBrainDocument))).all()) == 2
    await pi.close()


async def test_a_draft_that_breaks_the_rules_is_sent_back_once_then_flagged_for_the_reviewer(
    api, business_db, monkeypatch
):
    def sloppy(payload):
        refs = [p["ref"] for p in payload["problems"]]
        return SolutionDraft(
            components=[
                Component(text="This will increase your sales for Rs 500,000.", problems=refs[:1])
            ],
            wont_do=[],
        )

    pi, seen, conversation = await accepted_offer(api, business_db, monkeypatch, draft=sloppy)
    docs = await drafted(pi, business_db, conversation)
    assert len(seen["drafts"]) == 2  # one rewrite
    notes = docs["solution"].review_notes
    assert "R-DOC-09" in notes and "R-DOC-04" in notes and "R-DOC-03" in notes
    blocked = await api.post(f"{DOCS}/{docs['solution'].id}/approve")
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "DOCUMENT_NOT_READY"
    await pi.close()


async def test_nothing_is_approved_or_sent_without_a_reviewer(api, business_db, monkeypatch):
    pi, _, conversation = await accepted_offer(api, business_db, monkeypatch)
    docs = await drafted(pi, business_db, conversation)
    offer = docs["quote"].offer_id
    unready = await api.post(f"{DOCS}/{docs['quote'].id}/approve")
    assert unready.status_code == 409 and unready.json()["error"]["code"] == "DOCUMENT_NOT_READY"
    message = unready.json()["error"]["message"]
    for need in ("enter the total", "valid-until", "time estimate", "bank account"):
        assert need in message
    early = await api.post(f"{DOCS}/offers/{offer}/send")
    assert early.status_code == 409 and early.json()["error"]["code"] == "DOCUMENTS_NOT_APPROVED"
    await bank(api)
    await price(api, docs["quote"].id)
    await api.post(f"{DOCS}/{docs['quote'].id}/approve")
    one_only = await api.post(f"{DOCS}/offers/{offer}/send")  # the solution is still in review
    assert one_only.status_code == 409
    assert sent_of(pi, "document") == []
    # An approved document goes back to review when it is edited.
    edited = await api.patch(f"{DOCS}/{docs['quote'].id}", json={"cost": {"total": "460000"}})
    assert edited.json()["status"] == "in_review"
    await pi.close()


async def test_the_reviewer_cannot_enter_a_nonsense_price(api, business_db, monkeypatch):
    pi, _, conversation = await accepted_offer(api, business_db, monkeypatch)
    quote = (await drafted(pi, business_db, conversation))["quote"]
    for body, code in (
        ({"cost": {"total": "lots"}}, "INVALID_TOTAL"),
        ({"cost": {"currency": "rupees"}}, "INVALID_CURRENCY"),
        ({"valid_until": "soon"}, "INVALID_DATE"),
    ):
        refused = await api.patch(f"{DOCS}/{quote.id}", json=body)
        assert refused.status_code in (400, 422) and refused.json()["error"]["code"] == code
    await pi.close()


async def test_approved_documents_go_out_as_two_pdfs_and_the_three_buttons(
    api, business_db, monkeypatch
):
    pi, _, conversation = await accepted_offer(api, business_db, monkeypatch)
    docs = await drafted(pi, business_db, conversation)
    await approve_both(api, docs)
    approved = await business_db.get(PiBrainDocument, docs["quote"].id)
    await business_db.refresh(approved)
    assert approved.file_id is not None and approved.approved_by is not None
    sent = await api.post(f"{DOCS}/offers/{docs['quote'].offer_id}/send")
    assert sent.status_code == 200 and sent.json()["queued"] == 3
    await pi.deliver_all()
    documents = sent_of(pi, "document")
    assert [d["document"]["filename"] for d in documents] == ["SD-0001.pdf", "Q-0001.pdf"]
    assert documents[0]["document"]["caption"] == "Solution document SD-0001"
    cover = sent_of(pi, "interactive")[-1]["interactive"]
    assert "A quote is an offer, not a charge." in cover["body"]["text"]
    assert [b["reply"]["title"] for b in cover["action"]["buttons"]] == decisions.DECISION_BUTTONS[
        "en"
    ]
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert conversation.flow_state == "S7_DELIVERED"
    for kind in ("solution", "quote"):
        row = await business_db.get(PiBrainDocument, docs[kind].id)
        await business_db.refresh(row)
        assert row.status == "sent" and row.sent_at is not None
    again = await api.post(f"{DOCS}/offers/{docs['quote'].offer_id}/send")
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_SENT"
    await pi.close()


async def test_the_pdf_link_serves_only_the_approved_file(api, business_db, monkeypatch):
    pi, _, conversation = await accepted_offer(api, business_db, monkeypatch)
    docs = await drafted(pi, business_db, conversation)
    await approve_both(api, docs)
    await api.post(f"{DOCS}/offers/{docs['quote'].offer_id}/send")
    await pi.deliver_all()
    solution_link, quote_link = (d["document"]["link"] for d in sent_of(pi, "document"))
    public = _public(api)
    quote_pdf = await public.get(urlparse(quote_link).path)
    assert quote_pdf.status_code == 200 and quote_pdf.headers["content-type"] == "application/pdf"
    assert quote_pdf.content.startswith(b"%PDF") and b"PKR 450,000.00" in quote_pdf.content
    assert b"PK36SCBL0000001123456702" in quote_pdf.content  # bank details only on the quote
    solution_pdf = await public.get(urlparse(solution_link).path)
    assert solution_pdf.status_code == 200 and b"PK36" not in solution_pdf.content
    assert b"Best-sellers run out in two shops" in solution_pdf.content
    token, name = urlparse(quote_link).path.rsplit("/", 2)[-2:]
    assert (
        await public.get(f"/api/v1/pi-app/brain-docs/{token[:-3]}abc/{name}")
    ).status_code == 404
    assert (await public.get(f"/api/v1/pi-app/brain-docs/junk/{name}")).status_code == 404
    # No bank details in any chat message.
    assert not any("PK36" in json.dumps(m) for m in pi.sent)
    await pi.close()


async def test_an_unapproved_draft_has_no_public_link(api, business_db, monkeypatch):
    from app.modules.pi import brain_docs

    pi, _, conversation = await accepted_offer(api, business_db, monkeypatch)
    docs = await drafted(pi, business_db, conversation)
    token = brain_docs.doc_token(pi.app.state.settings, docs["quote"].id)
    public = _public(api)
    assert (await public.get(f"/api/v1/pi-app/brain-docs/{token}/Q-0001.pdf")).status_code == 404
    await pi.close()


async def test_approval_after_reading_needs_two_confirmations_on_the_real_quote(
    api, business_db, monkeypatch
):
    pi, _, conversation = await accepted_offer(api, business_db, monkeypatch)
    docs = await drafted(pi, business_db, conversation)
    await approve_both(api, docs)
    await api.post(f"{DOCS}/offers/{docs['quote'].offer_id}/send")
    await pi.deliver_all()
    await say(pi, "Approve", "dc-6")
    assert (await pi.reply_to("dc-6")).body == (
        "Just to confirm: you approve quote Q-0001 for PKR 450,000.00. Is that right?"
    )
    await say(pi, "yes", "dc-7")
    assert (await pi.reply_to("dc-7")).body == decisions.text("approved", "en")
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert conversation.flow_state == "S10_AWAITING_PAYMENT"
    assert conversation.service_brief["approval"]["quote"] == "Q-0001"
    approve = (
        await business_db.scalars(select(PiStaffRequest).where(PiStaffRequest.kind == "approve"))
    ).one()
    assert "Q-0001" in approve.question
    await pi.close()


async def test_asking_for_changes_brings_a_revised_quote_that_replaces_the_old_one(
    api, business_db, monkeypatch
):
    pi, seen, conversation = await accepted_offer(api, business_db, monkeypatch)
    docs = await drafted(pi, business_db, conversation)
    await approve_both(api, docs)
    await api.post(f"{DOCS}/offers/{docs['quote'].offer_id}/send")
    await pi.deliver_all()
    await say(pi, "Ask for changes", "ch-1")
    assert (await pi.reply_to("ch-1")).body == "What would you like changed?"
    await say(pi, "only 2 shops for now, not 3", "ch-2")
    assert "Noted: Cover 2 shops instead of 3." in (await pi.reply_to("ch-2")).body
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert conversation.flow_state == "S8b_CHANGES_REQUESTED"
    assert conversation.service_brief["revision_requested"]["changes"] == [
        "Cover 2 shops instead of 3"
    ]
    asked = (
        await business_db.scalars(
            select(PiStaffRequest).where(PiStaffRequest.question.contains("asked for changes"))
        )
    ).all()
    assert asked and "Cover 2 shops instead of 3" in asked[0].question

    # The reviewer makes version 2 of the quote with the new price, approves and sends it.
    pi.sent.clear()
    revised = await api.post(
        f"{DOCS}/{docs['quote'].id}/revise",
        json={"cost": {"total": "300000"}, "time": {"estimate": "About four weeks from kickoff"}},
    )
    assert revised.status_code == 201 and revised.json()["ref"] == "Q-0001-v2"
    v2 = revised.json()["id"]
    assert (await api.post(f"{DOCS}/{v2}/approve")).status_code == 200
    old = await business_db.get(PiBrainDocument, docs["quote"].id)
    await business_db.refresh(old)
    assert old.status == "superseded"
    out = await api.post(f"{DOCS}/offers/{docs['quote'].offer_id}/send")
    assert out.status_code == 200 and out.json()["queued"] == 2  # only the quote, and the cover
    await pi.deliver_all()
    assert [d["document"]["filename"] for d in sent_of(pi, "document")] == ["Q-0001-v2.pdf"]
    cover = sent_of(pi, "interactive")[-1]["interactive"]["body"]["text"]
    assert cover.startswith("Here is the revised version you asked for.")
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert conversation.flow_state == "S7_DELIVERED"

    # Approving now confirms the new quote, never the old one.
    await say(pi, "Approve", "ch-3")
    assert (await pi.reply_to("ch-3")).body == (
        "Just to confirm: you approve quote Q-0001-v2 for PKR 300,000.00. Is that right?"
    )
    # The superseded version is no longer served.
    stale = await business_db.get(PiBrainDocument, docs["quote"].id)
    from app.modules.pi import brain_docs

    token = brain_docs.doc_token(pi.app.state.settings, stale.id)
    assert (
        await _public(api).get(f"/api/v1/pi-app/brain-docs/{token}/Q-0001.pdf")
    ).status_code == 404
    await pi.close()


async def test_a_staff_preview_shows_the_pdf_before_approval(api, business_db, monkeypatch):
    pi, _, conversation = await accepted_offer(api, business_db, monkeypatch)
    docs = await drafted(pi, business_db, conversation)
    preview = await api.get(f"{DOCS}/{docs['solution'].id}/pdf")
    assert preview.status_code == 200 and preview.content.startswith(b"%PDF")
    listing = (await api.get(f"{DOCS}?status=in_review")).json()["items"]
    assert {i["ref"] for i in listing} == {"SD-0001", "Q-0001"}
    one = (await api.get(f"{DOCS}/{docs['quote'].id}")).json()
    assert one["blockers"] and one["total"] is None
    await pi.close()


async def test_the_draft_job_ignores_a_chat_that_has_no_accepted_offer(
    api, business_db, monkeypatch
):
    install_models(monkeypatch)
    pi = await workspace(api, business_db)
    await say(pi, "Best-sellers run out and cashiers are late on weekends", "nj-1")
    conversation = await pi.conversation()
    await draft_brain_documents(pi.ctx, str(conversation.id))
    assert (await business_db.scalars(select(PiBrainDocument))).all() == []
    await pi.close()


async def approved_and_waiting_for_payment(api, db, monkeypatch):
    pi, _, conversation = await accepted_offer(api, db, monkeypatch)
    docs = await drafted(pi, db, conversation)
    await approve_both(api, docs)
    await api.post(f"{DOCS}/offers/{docs['quote'].offer_id}/send")
    await pi.deliver_all()
    await say(pi, "Approve", "pay-1")
    await say(pi, "yes", "pay-2")
    return pi, docs


async def test_approval_opens_a_payment_and_only_staff_can_confirm_it(
    api, business_db, monkeypatch
):
    from app.modules.pi.brain_docs_models import PiBrainPayment

    pi, docs = await approved_and_waiting_for_payment(api, business_db, monkeypatch)
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert conversation.flow_state == "S10_AWAITING_PAYMENT"
    payment = (await business_db.scalars(select(PiBrainPayment))).one()
    assert payment.status == "pending" and payment.quote_id == docs["quote"].id

    # A question about paying is answered by the model, never treated as paying.
    await say(pi, "how do I pay?", "pay-3")
    assert (await pi.reply_to("pay-3")).body != decisions.text("payment_claimed", "en")
    await business_db.refresh(payment)
    assert payment.status == "pending"

    # "I have paid" is a claim: thanked, never confirmed, and the team is told.
    await say(pi, "I have paid the transfer", "pay-4")
    reply = (await pi.reply_to("pay-4")).body
    assert reply == "Thanks. The Workzap team will confirm here when the transfer arrives."
    await business_db.refresh(payment)
    assert payment.status == "claimed" and payment.claimed_at is not None
    await business_db.refresh(conversation)
    assert conversation.flow_state == "S10_AWAITING_PAYMENT"
    told = (
        await business_db.scalars(
            select(PiStaffRequest).where(PiStaffRequest.question.contains("says they paid"))
        )
    ).all()
    assert told and "Q-0001" in told[0].question
    assert not any("received" in json.dumps(m).lower() for m in pi.sent)

    listed = (await api.get(f"{DOCS}/payments?status=claimed")).json()["items"]
    assert [(i["quote_ref"], i["status"], i["total"]) for i in listed] == [
        ("Q-0001", "claimed", "450000.00")
    ]
    pi.sent.clear()
    done = await api.post(f"{DOCS}/payments/{payment.id}/confirm", json={"reference": "TRX-991"})
    assert (
        done.status_code == 200 and done.json()["status"] == "confirmed" and done.json()["notified"]
    )
    await pi.deliver_all()
    texts = [m["text"]["body"] for m in sent_of(pi, "text")]
    assert texts == [decisions.text("payment_confirmed", "en")]
    await business_db.refresh(payment)
    await business_db.refresh(conversation)
    assert payment.status == "confirmed" and payment.confirmed_by is not None
    assert payment.reference == "TRX-991" and conversation.flow_state == "S11_PAYMENT_CONFIRMED"
    assert conversation.service_brief["payment"]["status"] == "confirmed"
    again = await api.post(f"{DOCS}/payments/{payment.id}/confirm", json={})
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_CONFIRMED"
    await pi.close()


async def test_a_confirmation_outside_the_24_hour_window_is_told_when_they_next_write(
    api, business_db, monkeypatch
):
    from datetime import UTC, datetime, timedelta

    from app.modules.pi.brain_docs_models import PiBrainPayment

    pi, _ = await approved_and_waiting_for_payment(api, business_db, monkeypatch)
    conversation = await pi.conversation()
    conversation.last_inbound_at = datetime.now(UTC) - timedelta(hours=30)
    await business_db.commit()
    payment = (await business_db.scalars(select(PiBrainPayment))).one()
    pi.sent.clear()
    done = await api.post(f"{DOCS}/payments/{payment.id}/confirm", json={})
    assert done.status_code == 200 and done.json()["notified"] is False
    await pi.deliver_all()
    assert sent_of(pi, "text") == []  # nothing free-form may go outside the window
    await business_db.refresh(conversation)
    assert conversation.service_brief["payment_notice_due"] is True
    await say(pi, "hello", "pay-9")
    assert (await pi.reply_to("pay-9")).body == decisions.text("payment_confirmed", "en")
    await business_db.refresh(conversation)
    assert "payment_notice_due" not in conversation.service_brief
    await pi.close()


async def test_a_kickoff_slot_after_confirmed_payment_moves_to_kickoff(
    api, business_db, monkeypatch
):
    from app.modules.pi.brain_docs_models import PiBrainPayment
    from app.modules.pi.brain_payments import kickoff_booked

    pi, _ = await approved_and_waiting_for_payment(api, business_db, monkeypatch)
    conversation = await pi.conversation()
    assert kickoff_booked(conversation) is False  # not before payment is confirmed
    payment = (await business_db.scalars(select(PiBrainPayment))).one()
    await api.post(f"{DOCS}/payments/{payment.id}/confirm", json={})
    await business_db.refresh(conversation)
    assert kickoff_booked(conversation) is True
    assert conversation.flow_state == "S12_KICKOFF" and "kickoff" in conversation.service_brief
    assert kickoff_booked(conversation) is False
    await pi.close()
