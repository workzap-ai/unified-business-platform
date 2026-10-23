"""The solution document and quote in brain mode (pi Brain spec, Part 5).

pi drafts the solution document from the noted problems and checks it against R-DOC-01..09. The
quote is only a skeleton: prices come from a Workzap reviewer, never from pi (R-QUOTE-01). Nothing
reaches the person until a reviewer approves both (R-DOC-00): `approve` refuses a document that
breaks a rule, `send` refuses an unapproved one. A revision is a new version and the old one is
superseded (R-QUOTE-08).
"""

import base64
import hmac
import json
import logging
import re
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.manager import LLMManager
from app.ai.types import Message
from app.core.config import Settings
from app.modules.customers import files
from app.modules.customers.models import Customer
from app.modules.pi import brain_pdf, constitution, decisions, flow, industry_packs, problems
from app.modules.pi.brain_docs_models import PiBrainDocument
from app.modules.pi.models import PiConversation, PiMessage, WhatsAppConnection
from app.modules.pi.problem_models import PiProblem
from app.modules.pi_customer.access import _sign
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

logger = logging.getLogger("platform")

DOC_SECONDS = 30 * 86400
WINDOW = timedelta(hours=24)
CURRENCY = {"92": "PKR", "971": "AED", "1": "CAD"}
MAX_COMPONENT_WORDS = 40
MAX_SENTENCE_WORDS = 25

# An amount: a currency word or symbol, a grouped figure (450,000), a figure with k/lakh/crore/
# million, or a figure right after "cost", "price", "fee"... A year or a count ("4 shops") is not.
MONEY_IN_TEXT = re.compile(
    r"\b(?:rs\.?|pkr|aed|cad|usd|dirhams?|rupees?|lakhs?|crores?)\b|[$€£₹]"
    r"|\b\d{1,3}(?:,\d{2,3})+(?:\.\d+)?\b"
    r"|\b\d+(?:\.\d+)?\s?(?:k|m|lakh|lac|crore|million|thousand)\b"
    r"|\b(?:cost|costs|price|priced|fee|fees|charge|charged|budget|pay|paying)\b\D{0,15}\d{3,}",
    re.IGNORECASE,
)
WILL = re.compile(r"\bwill\b(?! not)", re.IGNORECASE)


class Component(BaseModel):
    text: str = Field(max_length=300)  # one plain English sentence, with "would"
    local: str = Field(default="", max_length=300)  # the same in the person's language
    problems: list[str] = Field(default_factory=list)  # refs of the problems it addresses


class WontDo(BaseModel):
    text: str = Field(max_length=300)
    local: str = Field(default="", max_length=300)
    problem: str = ""  # a problem this leaves alone, with the plain reason in text


class SolutionDraft(BaseModel):
    components: list[Component] = Field(default_factory=list, max_length=8)
    covers: list[str] = Field(default_factory=list, max_length=8)
    covers_local: list[str] = Field(default_factory=list, max_length=8)
    wont_do: list[WontDo] = Field(default_factory=list, max_length=8)
    needs: list[str] = Field(default_factory=list, max_length=6)
    needs_local: list[str] = Field(default_factory=list, max_length=6)


SYSTEM = """You write a solution document for a business owner who told pi, an AI on WhatsApp,
what is going wrong. A Workzap reviewer reads it before the owner does.
Rules:
- Plain words a twelve-year-old follows. No jargon (no KPI, SKU, ERP, workflow, stakeholder).
- "components": what Workzap would build, one plain sentence each, always with "would" (never
  "will"). Each names the refs of the problems it addresses in "problems". No component without
  a problem: no upsell.
- Every problem must be addressed by a component, or listed in "wont_do" with its ref in
  "problem" and a plain reason in "text".
- "wont_do" is never empty: say what this does not change (for example how they order from
  suppliers) and anything the person must confirm.
- "covers": the parts of the business it touches (shops, teams, channels, data).
- "needs": what Workzap would need from them (a contact person, sample data). Never ask for
  passwords or payment details in chat; access is arranged at kickoff.
- No price, no date, no promise of an outcome (never "will increase sales" or "you will save").
- text is English. When language is not English, local is the same sentence in that language
  (Roman Urdu uses everyday English business words); otherwise leave local empty.
- workzap_can_build lists internal ideas for this trade: use them to word components, never
  copy them if no problem needs them.
Return only the structured result."""


# --- numbering, tokens ------------------------------------------------------------------------


async def next_number(session: AsyncSession, scope: WorkspaceScope, kind: str) -> int:
    top = await session.scalar(
        select(func.max(PiBrainDocument.number)).where(
            PiBrainDocument.tenant_id == scope.tenant_id,
            PiBrainDocument.environment_id == scope.environment_id,
            PiBrainDocument.kind == kind,
        )
    )
    return int(top or 0) + 1


def doc_token(settings: Settings, doc_id: UUID) -> str:
    data = json.dumps(
        {"d": str(doc_id), "e": int(time.time()) + DOC_SECONDS}, separators=(",", ":")
    ).encode()
    return f"{base64.urlsafe_b64encode(data).decode().rstrip('=')}.{_sign(settings, data)}"


def read_doc_token(settings: Settings, token: str) -> UUID | None:
    try:
        body, mac = token.split(".", 1)
        data = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        if not hmac.compare_digest(mac, _sign(settings, data)):
            return None
        claims = json.loads(data)
        if int(claims["e"]) < time.time():
            return None
        return UUID(claims["d"])
    except (ValueError, KeyError, TypeError):
        return None


def doc_url(settings: Settings, doc: PiBrainDocument, english: bool = False) -> str:
    base = settings.pi_app_public_url.rstrip("/")
    name = f"{doc.ref}-EN.pdf" if english else f"{doc.ref}.pdf"
    return f"{base}/api/v1/pi-app/brain-docs/{doc_token(settings, doc.id)}/{name}"


# --- the rules (R-DOC-01..09) ------------------------------------------------------------------


def check_solution(draft: SolutionDraft, refs: set[str]) -> list[str]:
    """What breaks the document rules; empty means it is ready for a reviewer."""
    issues: list[str] = []
    if not draft.components:
        issues.append("there are no components: say what Workzap would build")
    addressed: set[str] = set()
    for component in draft.components:
        mapped = [r for r in component.problems if r in refs]
        if not mapped:
            issues.append(f'component "{component.text[:50]}" names no known problem (R-DOC-02)')
        addressed.update(mapped)
        if len(component.text.split()) > MAX_COMPONENT_WORDS:
            issues.append(f'component "{component.text[:50]}" is too long')
    left_alone = {w.problem for w in draft.wont_do if w.problem in refs}
    for ref in sorted(refs - addressed - left_alone):
        issues.append(f"problem {ref} is neither addressed nor listed under wont_do (R-DOC-03)")
    if not draft.wont_do:
        issues.append('"wont_do" is empty (R-DOC-04)')
    texts = [c.text for c in draft.components] + [w.text for w in draft.wont_do]
    texts += draft.covers + draft.needs
    for text in texts:
        if MONEY_IN_TEXT.search(text):
            issues.append(
                f'"{text[:50]}" has a price or amount: prices are only on the quote (R-DOC-09)'
            )
        if constitution.PROMISE.search(text):
            issues.append(f'"{text[:50]}" promises an outcome (R-DOC-06)')
        if WILL.search(text):
            issues.append(f'"{text[:50]}" says "will": use "would" (R-DOC-06)')
        if any(len(s.split()) > MAX_SENTENCE_WORDS for s in re.split(r"[.!?]", text)):
            issues.append(f'"{text[:50]}" has a sentence that is too long (R-DOC-05)')
        for term in constitution.JARGON:
            if re.search(rf"\b{re.escape(term)}s?\b", text, re.IGNORECASE):
                issues.append(f'"{text[:50]}" uses "{term}" (R-DOC-05)')
                break
    plain = " ".join(texts)
    grade = reading_grade(plain)
    if len(plain.split()) >= 30 and grade > MAX_READING_GRADE:
        issues.append(
            f"the document reads at about grade {grade:.0f}: use shorter sentences and everyday "
            f"words (the target is grade {MAX_READING_GRADE}, R-DOC-05)"
        )
    return issues


MAX_READING_GRADE = 9


def _syllables(word: str) -> int:
    groups = re.findall(r"[aeiouy]+", word.lower())
    count = len(groups) - (1 if word.lower().endswith("e") and len(groups) > 1 else 0)
    return max(1, count)


def reading_grade(text: str) -> float:
    """Flesch-Kincaid grade for English text (R-DOC-05: plain words, reading age about 12)."""
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    words = re.findall(r"[A-Za-z']+", text)
    if not sentences or not words:
        return 0.0
    syllables = sum(_syllables(w) for w in words)
    return 0.39 * len(words) / len(sentences) + 11.8 * syllables / len(words) - 15.59


def check_content(content: dict[str, Any], refs: set[str] | None = None) -> list[str]:
    """The same rules on a stored (possibly edited) solution content."""
    draft = SolutionDraft(
        components=[
            Component(text=c.get("text", ""), problems=c.get("refs", []))
            for c in content.get("components", [])
        ],
        covers=[str(x) for x in content.get("covers", [])],
        wont_do=[
            WontDo(text=w.get("text", ""), problem=w.get("problem", ""))
            for w in content.get("wont_do", [])
        ],
        needs=[str(x) for x in content.get("needs", [])],
    )
    known = refs if refs is not None else {p["ref"] for p in content.get("problems", [])}
    return check_solution(draft, known)


# --- drafting ---------------------------------------------------------------------------------


def _line(problem: PiProblem, language: str) -> str:
    bits = []
    where = ", ".join((problem.scope or {}).get("where") or []) or (problem.scope or {}).get(
        "of_total"
    )
    if where:
        bits.append(f"Where: {where}")
    if (problem.frequency or {}).get("text"):
        bits.append(f"How often: {problem.frequency['text']}")
    if (problem.since or {}).get("text"):
        bits.append(f"Since: {problem.since['text']}")
    return " | ".join(bits)


def solution_content(
    draft: SolutionDraft,
    rows: list[PiProblem],
    *,
    business: str,
    ref: str,
    language: str,
    local: bool,
) -> dict[str, Any]:
    """The stored document. Section 1 uses the person's own words (R-DOC-01); section 6 is fixed."""
    titles = {problems.short_ref(p.id): p.title for p in rows}

    def pick(text: str, other: str) -> str:
        return other if local and other.strip() else text

    return {
        "ref": ref,
        "business": business,
        "date": date.today().isoformat(),
        "language": language if local else "en",
        "problems": [
            {
                "ref": problems.short_ref(p.id),
                "title": (p.title_local if local and p.title_local else p.title),
                "quotes": list(p.user_words[:2]),
                "line": _line(p, language),
            }
            for p in rows
        ],
        "components": [
            {
                "text": pick(c.text, c.local),
                "refs": [r for r in c.problems if r in titles],
                "problems": [titles[r] for r in c.problems if r in titles],
            }
            for c in draft.components
        ],
        "covers": [
            (draft.covers_local[i] if local and i < len(draft.covers_local) else text)
            for i, text in enumerate(draft.covers)
        ],
        "wont_do": [
            {"text": pick(w.text, w.local), "problem": w.problem if w.problem in titles else ""}
            for w in draft.wont_do
        ],
        "needs": [
            (draft.needs_local[i] if local and i < len(draft.needs_local) else text)
            for i, text in enumerate(draft.needs)
        ],
    }


def quote_content(solution: dict[str, Any], currency: str) -> dict[str, Any]:
    """The quote's skeleton: what is included and what is not come from the document; every price,
    date and duration is left for the reviewer (R-QUOTE-01)."""
    return {
        "solution_ref": solution["ref"],
        "included": [c["text"] for c in solution.get("components", [])],
        "cost": {"total": None, "currency": currency, "tax_text": "", "instalments": []},
        "time": {"estimate": "", "milestones": []},
        "payment": "Payment is by bank transfer only. The bank details are on this quote.",
        "not_included": [w["text"] for w in solution.get("wont_do", [])],
        "decide": "Approve, ask for changes, or say no.",
        "note": "A quote is an offer. It isn't a charge.",
    }


def currency_for(customer: Customer) -> str:
    """PKR, AED or CAD from the number (R-QUOTE-07); the reviewer can change it."""
    phone = (customer.phone or customer.whatsapp_id or "").lstrip("+")
    for prefix, code in CURRENCY.items():
        if phone.startswith(prefix):
            return code
    return ""


async def _complete(
    manager: LLMManager, scope: WorkspaceScope, payload: dict[str, Any], notes: list[str] | None
) -> SolutionDraft:
    messages = [Message.system(SYSTEM), Message.user(json.dumps(payload, ensure_ascii=False))]
    if notes:
        messages.append(
            Message.user("Fix these and return the whole result again: " + "; ".join(notes))
        )
    result = await manager.complete_structured(
        scope,
        SolutionDraft,
        alias="balanced",
        purpose="pi_solution_doc",
        messages=messages,
        temperature=0.2,
        max_tokens=4096,
    )
    value: SolutionDraft = result.value
    return value


async def draft_offer(
    session: AsyncSession,
    scope: WorkspaceScope,
    manager: LLMManager,
    conversation_id: UUID,
) -> tuple[PiBrainDocument, PiBrainDocument] | None:
    """Draft the solution document and the quote skeleton for the problems the person chose.
    Both land in review; neither is shown to the person. None when there is nothing to do."""
    conversation = await WorkspaceRepository(session, PiConversation, scope).get(conversation_id)
    brief = conversation.service_brief or {}
    offer = brief.get("offer") or {}
    if not offer or offer.get("offer_id") or conversation.customer_id is None:
        return None  # no yes recorded, or already drafted
    customer = await WorkspaceRepository(session, Customer, scope).get(conversation.customer_id)
    book = problems.ProblemBook(session, scope, customer.id, "en")
    wanted = set(offer.get("problem_refs") or [])
    rows = [p for p in await book.active() if not wanted or problems.short_ref(p.id) in wanted]
    if not rows:
        return None
    language = conversation.language or "en"
    business = (
        (brief.get("customer_profile") or {}).get("business_name")
        or customer.company
        or "Your business"
    )
    pack = industry_packs.get_pack(customer.industry_primary or "")
    payload = {
        "language": language,
        "business": business,
        "problems": [
            {
                "ref": problems.short_ref(p.id),
                "title": p.title,
                "category": p.category,
                "subtype": p.subtype,
                "their_words": p.user_words[:2],
                "where": (p.scope or {}).get("where"),
                "impact": (p.impact or {}).get("types"),
            }
            for p in rows
        ],
        "workzap_can_build": industry_packs.build_ideas(pack)[:10] if pack else [],
    }
    refs = {problems.short_ref(p.id) for p in rows}
    draft = await _complete(manager, scope, payload, None)
    issues = check_solution(draft, refs)
    if issues:
        draft = await _complete(manager, scope, payload, issues)
        issues = check_solution(draft, refs)
    offer_id = uuid4()
    number = await next_number(session, scope, "solution")
    q_number = await next_number(session, scope, "quote")
    local = language != "en"
    repo = WorkspaceRepository(session, PiBrainDocument, scope)
    sol_ref = f"SD-{number:04d}"
    solution = await repo.add(
        repo.new(
            customer_id=customer.id,
            conversation_id=conversation.id,
            offer_id=offer_id,
            kind="solution",
            number=number,
            problem_ids=[str(p.id) for p in rows],
            language=language,
            content=solution_content(
                draft, rows, business=business, ref=sol_ref, language=language, local=local
            ),
            content_en=solution_content(
                draft, rows, business=business, ref=sol_ref, language=language, local=False
            )
            if local
            else {},
            status="in_review",
            drafted_by="pi",
            review_notes="; ".join(issues),
        )
    )
    english = solution.content_en or solution.content
    quote = await repo.add(
        repo.new(
            customer_id=customer.id,
            conversation_id=conversation.id,
            offer_id=offer_id,
            kind="quote",
            number=q_number,
            solution_id=solution.id,
            problem_ids=solution.problem_ids,
            language=language,
            content=quote_content(solution.content, currency_for(customer)),
            content_en=quote_content(english, currency_for(customer)) if local else {},
            currency=currency_for(customer),
            status="in_review",
            drafted_by="pi",
        )
    )
    conversation.service_brief = {
        **brief,
        "offer": {**offer, "offer_id": str(offer_id), "drafted_at": datetime.now(UTC).isoformat()},
    }
    return solution, quote


# --- the reviewer ------------------------------------------------------------------------------


async def documents_of(
    session: AsyncSession, scope: WorkspaceScope, offer_id: UUID
) -> list[PiBrainDocument]:
    repo = WorkspaceRepository(session, PiBrainDocument, scope)
    rows = await session.scalars(
        repo.select()
        .where(PiBrainDocument.offer_id == offer_id)
        .order_by(PiBrainDocument.kind.desc(), PiBrainDocument.version)
    )
    return list(rows)


def _decimal(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def edit(doc: PiBrainDocument, patch: dict[str, Any]) -> None:
    """A reviewer's edits to a draft. Solution: components, covers, wont_do, needs. Quote: included,
    not_included, cost (total, currency, tax_text, instalments), time (estimate, milestones),
    payment, valid_until. Editing sends an approved document back to review."""
    if doc.status in ("sent", "superseded"):
        raise BusinessRuleViolation("DOCUMENT_LOCKED", "This version was sent: make a new version")
    content = json.loads(json.dumps(doc.content))
    if doc.kind == "solution":
        for key in ("covers", "needs"):
            if key in patch:
                content[key] = [str(x)[:300] for x in patch[key]][:8]
        if "components" in patch:
            titles = {p["ref"]: p["title"] for p in content.get("problems", [])}
            content["components"] = [
                {
                    "text": str(c.get("text", ""))[:300],
                    "refs": [r for r in c.get("refs", []) if r in titles],
                    "problems": [titles[r] for r in c.get("refs", []) if r in titles],
                }
                for c in patch["components"]
            ][:8]
        if "wont_do" in patch:
            content["wont_do"] = [
                {"text": str(w.get("text", ""))[:300], "problem": str(w.get("problem", ""))}
                for w in patch["wont_do"]
            ][:8]
    else:
        for key in ("included", "not_included"):
            if key in patch:
                content[key] = [str(x)[:300] for x in patch[key]][:12]
        if "payment" in patch:
            content["payment"] = str(patch["payment"])[:500]
        if "cost" in patch:
            cost = dict(content.get("cost") or {})
            for key in ("tax_text",):
                if key in patch["cost"]:
                    cost[key] = str(patch["cost"][key])[:300]
            if "instalments" in patch["cost"]:
                cost["instalments"] = [str(x)[:200] for x in patch["cost"]["instalments"]][:6]
            if "total" in patch["cost"]:
                total = _decimal(patch["cost"]["total"])
                if total is None or total <= 0:
                    raise BusinessRuleViolation(
                        "INVALID_TOTAL", "The total must be a positive amount"
                    )
                doc.total = total.quantize(Decimal("0.01"))
                cost["total"] = str(doc.total)
            if "currency" in patch["cost"]:
                code = str(patch["cost"]["currency"]).upper()
                if not re.fullmatch(r"[A-Z]{3}", code):
                    raise BusinessRuleViolation("INVALID_CURRENCY", "Use a 3-letter currency code")
                doc.currency = cost["currency"] = code
            content["cost"] = cost
        if "time" in patch:
            time_ = dict(content.get("time") or {})
            if "estimate" in patch["time"]:
                time_["estimate"] = str(patch["time"]["estimate"])[:300]
            if "milestones" in patch["time"]:
                time_["milestones"] = [str(x)[:200] for x in patch["time"]["milestones"]][:8]
            content["time"] = time_
        if "valid_until" in patch:
            try:
                doc.valid_until = date.fromisoformat(str(patch["valid_until"]))
            except ValueError:
                raise BusinessRuleViolation("INVALID_DATE", "Use a date like 2026-12-31") from None
    doc.content = content
    if "review_notes" in patch:
        doc.review_notes = str(patch["review_notes"])[:1000]
    doc.status = "in_review"
    doc.approved_by = None
    doc.approved_at = None
    doc.drafted_by = "staff" if doc.drafted_by == "pi" else doc.drafted_by


async def bank_accounts(session: AsyncSession, scope: WorkspaceScope) -> list[dict[str, Any]]:
    from app.modules.pi_saas.customer_payment_models import PiCustomerPaymentSettings

    row = await WorkspaceRepository(session, PiCustomerPaymentSettings, scope).find()
    if row is None or not row.bank_enabled:
        return []
    return [a for a in row.bank_accounts if a.get("account_number") or a.get("iban")]


async def blockers(session: AsyncSession, scope: WorkspaceScope, doc: PiBrainDocument) -> list[str]:
    """Why this document cannot be approved yet (empty = it can)."""
    if doc.kind == "solution":
        return check_content(doc.content)
    issues: list[str] = []
    cost = doc.content.get("cost") or {}
    if doc.total is None or doc.total <= 0:
        issues.append("enter the total")
    if not doc.currency:
        issues.append("choose the currency")
    if doc.valid_until is None or doc.valid_until < date.today():
        issues.append("set a valid-until date that is not in the past")
    if not (doc.content.get("time") or {}).get("estimate", "").strip():
        issues.append("write the time estimate")
    if not doc.content.get("included"):
        issues.append("list what is included")
    if not doc.content.get("not_included"):
        issues.append("list what is not included (mirror the document)")
    if not await bank_accounts(session, scope):
        issues.append(
            "set up a bank account for payments first: bank details are printed on the quote"
        )
    if cost.get("total") is None and doc.total is not None:
        issues.append("the total on the page and in the content differ")
    return issues


async def render_pdf(
    session: AsyncSession, scope: WorkspaceScope, doc: PiBrainDocument, english: bool = False
) -> tuple[bytes, str]:
    language = (
        "en" if english else (doc.language if doc.language in brain_pdf.PDF_LANGUAGES else "en")
    )
    content = (
        (doc.content_en or doc.content) if english or language != doc.language else doc.content
    )
    customer = await WorkspaceRepository(session, Customer, scope).get(doc.customer_id)
    business = content.get("business") or customer.company or "Your business"
    issued = (doc.approved_at or datetime.now(UTC)).date()
    suffix = "-EN" if english else ""
    if doc.kind == "solution":
        return (
            brain_pdf.render_solution(
                content, business=business, ref=doc.ref, issued=issued, language=language
            ),
            f"{doc.ref}{suffix}.pdf",
        )
    solution = await session.get(PiBrainDocument, doc.solution_id) if doc.solution_id else None
    connection = await WorkspaceRepository(session, WhatsAppConnection, scope).find()
    return (
        brain_pdf.render_quote(
            content,
            business=business,
            ref=doc.ref,
            solution_ref=solution.ref if solution else "",
            issued=issued,
            valid_until=doc.valid_until,
            total=doc.total,
            currency=doc.currency,
            language=language,
            banks=await bank_accounts(session, scope),
            phone=connection.display_phone_number if connection else None,
        ),
        f"{doc.ref}{suffix}.pdf",
    )


async def approve(
    session: AsyncSession, scope: WorkspaceScope, doc: PiBrainDocument, user_id: UUID | None
) -> PiBrainDocument:
    """A reviewer's approval (R-DOC-00): refused while a rule is broken or a price is missing.
    The PDF is rendered now and kept, so what was approved is exactly what is sent."""
    if doc.status in ("sent", "superseded"):
        raise BusinessRuleViolation("DOCUMENT_LOCKED", "This version was already sent")
    issues = await blockers(session, scope, doc)
    if issues:
        raise BusinessRuleViolation(
            "DOCUMENT_NOT_READY", "Not ready to approve: " + "; ".join(issues), 409
        )
    doc.status = "approved"
    doc.approved_by = user_id
    doc.approved_at = datetime.now(UTC)
    data, name = await render_pdf(session, scope, doc)
    saved = await files.save(
        session,
        scope,
        doc.customer_id,
        data,
        name,
        "upload",
        conversation_id=doc.conversation_id,
        ref_type="brain_document",
        ref_id=doc.id,
    )
    doc.file_id = saved.id
    if doc.language != "en" and doc.content_en:
        # R-DOC-07: the team works from English, so an English copy is kept and sent too.
        english, english_name = await render_pdf(session, scope, doc, english=True)
        copy = await files.save(
            session,
            scope,
            doc.customer_id,
            english,
            english_name,
            "upload",
            conversation_id=doc.conversation_id,
            ref_type="brain_document",
            ref_id=doc.id,
        )
        doc.content = {**doc.content, "en_file_id": str(copy.id)}
    return doc


async def revise(
    session: AsyncSession, scope: WorkspaceScope, doc: PiBrainDocument, patch: dict[str, Any]
) -> PiBrainDocument:
    """A new version (R-QUOTE-08): the old one is superseded. A quote revision follows the latest
    solution version; revising the solution leaves its quote to be re-priced."""
    repo = WorkspaceRepository(session, PiBrainDocument, scope)
    newest = await session.scalar(
        select(func.max(PiBrainDocument.version)).where(
            PiBrainDocument.tenant_id == scope.tenant_id,
            PiBrainDocument.environment_id == scope.environment_id,
            PiBrainDocument.kind == doc.kind,
            PiBrainDocument.number == doc.number,
        )
    )
    doc.status = "superseded"
    fresh = await repo.add(
        repo.new(
            customer_id=doc.customer_id,
            conversation_id=doc.conversation_id,
            offer_id=doc.offer_id,
            kind=doc.kind,
            number=doc.number,
            version=int(newest or doc.version) + 1,
            solution_id=doc.solution_id,
            problem_ids=doc.problem_ids,
            language=doc.language,
            content=json.loads(json.dumps(doc.content)),
            content_en=json.loads(json.dumps(doc.content_en)),
            total=doc.total,
            currency=doc.currency,
            valid_until=doc.valid_until,
            status="in_review",
            drafted_by="staff",
            review_notes=doc.review_notes,
        )
    )
    if patch:
        edit(fresh, patch)
    return fresh


# --- sending ------------------------------------------------------------------------------------


COVER = {
    "en": (
        "Your solution document and quote are ready.\n"
        "• The document sets out what Workzap would build for the {n} problems you chose.\n"
        "• The quote says what's included, what it costs, and how long it takes.\n"
        "A quote is an offer, not a charge. You can approve, ask for changes, or say no."
    ),
    "roman_ur": (
        "Aap ka solution document aur quote tayyar hain.\n"
        "• Document mein likha hai ke Workzap aap ke chune hue {n} masail ke liye kya banayega.\n"
        "• Quote mein hai kya shamil hai, kitna kharcha hai, aur kitna waqt lagega.\n"
        "Quote ek offer hai, charge nahi. Aap manzoor kar sakte hain, tabdeeli maang sakte hain, "
        "ya mana kar sakte hain."
    ),
}


REVISED = {
    "en": (
        "Here is the revised version you asked for.\n"
        "A quote is an offer, not a charge. You can approve, ask for changes, or say no."
    ),
    "roman_ur": (
        "Ye aap ki maangi hui nayi version hai.\n"
        "Quote ek offer hai, charge nahi. Aap manzoor kar sakte hain, tabdeeli maang sakte hain, "
        "ya mana kar sakte hain."
    ),
}
CAPTION = {
    "en": {"solution": "Solution document", "quote": "Quote"},
    "roman_ur": {"solution": "Solution document", "quote": "Quote"},
}


async def latest_pair(
    session: AsyncSession, scope: WorkspaceScope, offer_id: UUID
) -> tuple[PiBrainDocument | None, PiBrainDocument | None]:
    rows = [d for d in await documents_of(session, scope, offer_id) if d.status != "superseded"]
    solution = next((d for d in rows if d.kind == "solution"), None)
    quote = next((d for d in rows if d.kind == "quote"), None)
    return solution, quote


async def send(
    session: AsyncSession, scope: WorkspaceScope, settings: Settings, offer_id: UUID
) -> list[str]:
    """Send the approved pair as two PDFs and a cover message with the three decision buttons
    (spec 5.5). Returns the queued message ids; the caller enqueues them."""
    solution, quote = await latest_pair(session, scope, offer_id)
    if solution is None or quote is None:
        raise BusinessRuleViolation("DOCUMENTS_MISSING", "There is no solution document and quote")
    if {solution.status, quote.status} - {"approved", "sent"}:
        raise BusinessRuleViolation(
            "DOCUMENTS_NOT_APPROVED", "A reviewer must approve both before they are sent", 409
        )
    # A revision sends only the version that changed: the other one is already with them.
    fresh = [d for d in (solution, quote) if d.status == "approved"]
    if not fresh:
        raise BusinessRuleViolation(
            "ALREADY_SENT",
            "These versions were already sent: make a new version to change them",
            409,
        )
    conversation = await WorkspaceRepository(session, PiConversation, scope).get(
        solution.conversation_id  # type: ignore[arg-type]
    )
    now = datetime.now(UTC)
    if not conversation.last_inbound_at or conversation.last_inbound_at < now - WINDOW:
        raise BusinessRuleViolation(
            "OUTSIDE_WINDOW",
            "The customer has not written in 24 hours, so WhatsApp only allows an approved "
            "template. Ask them to reply, then send again.",
            409,
        )
    language = conversation.language if conversation.language in COVER else "en"
    ids: list[str] = []
    for doc in fresh:
        label = CAPTION[language][doc.kind]
        ids.append(
            await queue_message(
                session,
                scope,
                conversation,
                f"{label} {doc.ref}",
                f"pi-brain-doc:{doc.id}",
                {"document": {"link": doc_url(settings, doc), "filename": f"{doc.ref}.pdf"}},
            )
        )
        if doc.content.get("en_file_id"):  # R-DOC-07: an English copy next to theirs
            ids.append(
                await queue_message(
                    session,
                    scope,
                    conversation,
                    f"{label} {doc.ref} (English)",
                    f"pi-brain-doc-en:{doc.id}",
                    {
                        "document": {
                            "link": doc_url(settings, doc, english=True),
                            "filename": f"{doc.ref}-EN.pdf",
                        }
                    },
                )
            )
        doc.status = "sent"
        doc.sent_at = now
    revised = len(fresh) < 2
    cover = (REVISED if revised else COVER)[language].format(n=len(solution.problem_ids))
    buttons = decisions.DECISION_BUTTONS.get(language, decisions.DECISION_BUTTONS["en"])
    ids.append(
        await queue_message(
            session,
            scope,
            conversation,
            cover,
            f"pi-brain-cover:{quote.id}",
            {"buttons": buttons},
        )
    )
    brief = dict(conversation.service_brief or {})
    brief["offer"] = {**(brief.get("offer") or {}), "sent_at": now.isoformat(), "quote": quote.ref}
    brief.pop("approval_pending", None)
    conversation.service_brief = brief
    current = flow.parse(conversation.flow_state)
    if current in (flow.State.S6_PREPARING, flow.State.S8B_CHANGES_REQUESTED):
        conversation.flow_state = flow.State.S7_DELIVERED.value
        conversation.flow_state_since = now
    return ids


async def queue_message(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    body: str,
    key: str,
    media: dict[str, Any],
) -> str:
    repo = WorkspaceRepository(session, PiMessage, scope)
    existing = await repo.find(PiMessage.idempotency_key == key)
    if existing is not None:
        return str(existing.id)
    message = await repo.add(
        repo.new(
            conversation_id=conversation.id,
            direction="outbound",
            sender_type="system",
            body=body,
            media=media,
            status="queued",
            idempotency_key=key,
        )
    )
    conversation.last_message_at = datetime.now(UTC)
    conversation.last_message_preview = body[:200]
    return str(message.id)


# --- what pi knows while the person reads --------------------------------------------------------


async def open_quote(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID
) -> dict[str, Any] | None:
    """The quote the person is reading: sent and not superseded. pi quotes only what is printed."""
    repo = WorkspaceRepository(session, PiBrainDocument, scope)
    quote = await session.scalar(
        repo.select()
        .where(
            PiBrainDocument.customer_id == customer_id,
            PiBrainDocument.kind == "quote",
            PiBrainDocument.status == "sent",
        )
        .order_by(PiBrainDocument.sent_at.desc())
        .limit(1)
    )
    if quote is None:
        return None
    solution = await session.get(PiBrainDocument, quote.solution_id) if quote.solution_id else None
    content = {k: v for k, v in quote.content.items() if k not in ("decide", "note")}
    return {
        "id": quote.ref,
        "total": brain_pdf.money(quote.total, quote.currency),
        "valid_until": quote.valid_until.isoformat() if quote.valid_until else None,
        "quote": content,
        "solution": {
            "ref": solution.ref,
            "components": [c["text"] for c in solution.content.get("components", [])],
            "wont_do": [w["text"] for w in solution.content.get("wont_do", [])],
            "covers": solution.content.get("covers", []),
        }
        if solution
        else None,
    }
