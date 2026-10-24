"""Several people from one business (pi Brain spec 4.9, R-MEM-06).

Each contact keeps their own conversation and memory. A business groups contacts: the first
person to name it becomes its owner; anyone else who names the same business joins once the
owner (or an authorised admin) approves, or Workzap staff links them directly. A joining member
is told once that their problems are shared with the owner; if they object, their problems stay
private (`shares_with_business = False`) and are never linked or counted below.

Only the owner or an admin may say yes to a document or approve a quote: `can_approve_for`
replaces reading `Customer.can_approve` on its own wherever the contact belongs to a business.

Problems different team members raise about the same thing are linked with the
`duplicate_across_contacts` type (`taxonomy.LINK_TYPES`) so the owner can be told "mentioned by
N people" (`mentioned_by`) without ever naming who said what: no consent-to-be-named mechanism
exists yet, so a name is never attached, which is the safe default the spec requires.
"""

import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import Customer
from app.modules.pi.business_models import PiBusiness
from app.modules.pi.problem_models import PiProblem, PiProblemLink
from app.modules.pi.taxonomy import STATUSES
from app.shared.scope import WorkspaceScope

LINKABLE_STATUSES = frozenset(STATUSES) - {"merged", "split", "withdrawn"}
TITLE_OVERLAP = 0.5  # share of the shorter title's words the two must have in common

DISCLOSURE = {
    "en": (
        "Problems you tell me will be shared with {business}'s owner so they can be sorted "
        "together."
    ),
    "roman_ur": (
        "Aap ke bataye hue masail {business} ke owner ke saath share honge, taake unhein "
        "ikatha sort kiya ja sake."
    ),
}

OBJECTS_TO_SHARING = re.compile(
    r"\b(?:don'?t|do not|never) (?:tell|share|send)\b.*\b(?:owner|boss|manager)\b"
    r"|\bkeep (?:this|it|that) (?:private|between us|to myself)\b"
    r"|\b(?:owner|boss|manager) ko (?:mat|na) bata\w*\b|\bprivate rakh\w*\b",
    re.IGNORECASE,
)


def normalize(name: str) -> str:
    return " ".join(name.casefold().split())


async def find_business(
    session: AsyncSession, scope: WorkspaceScope, name: str
) -> PiBusiness | None:
    result = await session.scalar(
        select(PiBusiness).where(
            PiBusiness.tenant_id == scope.tenant_id,
            PiBusiness.environment_id == scope.environment_id,
            PiBusiness.name_key == normalize(name),
        )
    )
    return result


async def join_or_request(
    session: AsyncSession, scope: WorkspaceScope, customer: Customer, business_name: str
) -> tuple[PiBusiness, bool]:
    """The contact names a business (spec 4.9). The first to name it owns it; anyone after that
    is recorded as awaiting approval. Returns (business, became_owner_immediately)."""
    existing = await find_business(session, scope, business_name)
    if existing is None:
        business = PiBusiness(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            name=business_name.strip()[:160],
            name_key=normalize(business_name),
        )
        session.add(business)
        await session.flush()  # business.id is only populated after flush
        customer.business_id = business.id
        customer.business_role = "owner"
        customer.business_joined_at = datetime.now(UTC)
        customer.pending_business_name = None
        return business, True
    customer.pending_business_name = business_name.strip()[:160]
    return existing, False


async def approve_join(
    session: AsyncSession, scope: WorkspaceScope, approver: Customer, applicant: Customer
) -> bool:
    """`approver` (the owner or an admin) approves `applicant`'s pending request to join their
    business. False when the approver cannot approve, or there is no matching pending request."""
    if approver.business_id is None or approver.business_role not in ("owner", "admin"):
        return False
    if applicant.pending_business_name is None:
        return False
    business = await session.get(PiBusiness, approver.business_id)
    if business is None or normalize(applicant.pending_business_name) != business.name_key:
        return False
    staff_link(applicant, business)
    return True


def staff_link(customer: Customer, business: PiBusiness) -> None:
    """Workzap staff link a contact to a business directly, bypassing owner approval."""
    customer.business_id = business.id
    customer.business_role = customer.business_role or "member"
    customer.business_joined_at = datetime.now(UTC)
    customer.pending_business_name = None


def disclosure_due(customer: Customer) -> bool:
    """Whether this contact's first message after joining still needs the sharing notice."""
    return (
        customer.business_id is not None
        and customer.business_role != "owner"
        and customer.shares_with_business
        and customer.business_disclosed_at is None
    )


def disclosure_text(business_name: str, language: str) -> str:
    lang = "roman_ur" if language == "roman_ur" else "en"
    return DISCLOSURE[lang].format(business=business_name)


def mark_disclosed(customer: Customer) -> None:
    customer.business_disclosed_at = datetime.now(UTC)


def objects_to_sharing(message: str) -> bool:
    return bool(OBJECTS_TO_SHARING.search(message))


def opt_out(customer: Customer) -> None:
    """They objected to sharing (spec 4.9): keep their problems private from here on."""
    customer.shares_with_business = False


def can_approve_for(customer: Customer) -> bool:
    """May this contact say yes to a document and approve a quote? A business role, where one
    applies, decides it; a contact with no business keeps their own `can_approve` flag."""
    if customer.business_id is None:
        return bool(customer.can_approve)
    return bool(customer.can_approve) and customer.business_role in ("owner", "admin")


def _title_words(problem: PiProblem) -> set[str]:
    return set(re.findall(r"[a-z]{3,}", problem.title.lower()))


def _overlaps(a: PiProblem, b: PiProblem) -> bool:
    words_a, words_b = _title_words(a), _title_words(b)
    if not words_a or not words_b:
        return False
    shorter = min(len(words_a), len(words_b))
    return len(words_a & words_b) / shorter >= TITLE_OVERLAP


async def find_business_mates(
    session: AsyncSession, scope: WorkspaceScope, customer: Customer
) -> list[UUID]:
    """Other contacts in the same shared business who have not opted out, excluding `customer`."""
    if customer.business_id is None or not customer.shares_with_business:
        return []
    rows = await session.scalars(
        select(Customer.id).where(
            Customer.tenant_id == scope.tenant_id,
            Customer.environment_id == scope.environment_id,
            Customer.business_id == customer.business_id,
            Customer.shares_with_business.is_(True),
            Customer.id != customer.id,
        )
    )
    return list(rows)


async def link_duplicates_for_problem(
    session: AsyncSession, scope: WorkspaceScope, problem: PiProblem
) -> list[PiProblemLink]:
    """`link_duplicates`, loading the problem's own customer first. The one extra lookup only
    happens when a problem is freshly created, never on every turn."""
    customer = await session.get(Customer, problem.customer_id)
    if customer is None or customer.business_id is None:
        return []
    return await link_duplicates(session, scope, problem, customer)


async def link_duplicates(
    session: AsyncSession, scope: WorkspaceScope, problem: PiProblem, customer: Customer
) -> list[PiProblemLink]:
    """A fresh problem, matched by category and title against the business's other members'
    problems (spec 4.9, `duplicate_across_contacts`). Confirmed outright: this is a deterministic
    match on their own words, not a model suggestion needing staff review."""
    mates = await find_business_mates(session, scope, customer)
    if not mates or problem.status not in LINKABLE_STATUSES:
        return []
    candidates = await session.scalars(
        select(PiProblem).where(
            PiProblem.tenant_id == scope.tenant_id,
            PiProblem.environment_id == scope.environment_id,
            PiProblem.customer_id.in_(mates),
            PiProblem.category == problem.category,
            PiProblem.status.in_(LINKABLE_STATUSES),
        )
    )
    created: list[PiProblemLink] = []
    for other in candidates:
        if not _overlaps(problem, other):
            continue
        a, b = sorted((problem.id, other.id), key=str)
        found = await session.scalar(
            select(PiProblemLink.id).where(
                PiProblemLink.tenant_id == scope.tenant_id,
                PiProblemLink.environment_id == scope.environment_id,
                PiProblemLink.from_id == a,
                PiProblemLink.to_id == b,
                PiProblemLink.type == "duplicate_across_contacts",
            )
        )
        if found is not None:
            continue
        link = PiProblemLink(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            from_id=a,
            to_id=b,
            type="duplicate_across_contacts",
            status="confirmed",
            created_by="pi",
        )
        session.add(link)
        created.append(link)
    return created


async def mentioned_by(session: AsyncSession, scope: WorkspaceScope, problem: PiProblem) -> int:
    """How many distinct contacts raised this problem (itself plus every contact it is linked to
    as a duplicate), never who they are (spec 4.9: "mentioned by N people", nobody named)."""
    rows = await session.execute(
        select(PiProblemLink.from_id, PiProblemLink.to_id).where(
            PiProblemLink.tenant_id == scope.tenant_id,
            PiProblemLink.environment_id == scope.environment_id,
            PiProblemLink.type == "duplicate_across_contacts",
            PiProblemLink.status == "confirmed",
            (PiProblemLink.from_id == problem.id) | (PiProblemLink.to_id == problem.id),
        )
    )
    problem_ids = {problem.id, *(pid for pair in rows.all() for pid in pair)}
    customers = await session.scalars(
        select(PiProblem.customer_id).where(
            PiProblem.tenant_id == scope.tenant_id,
            PiProblem.environment_id == scope.environment_id,
            PiProblem.id.in_(problem_ids),
        )
    )
    return len(set(customers))
