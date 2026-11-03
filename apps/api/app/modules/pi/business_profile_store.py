"""Keeping the Business Profile in the database (platform spec v1.4, 16.3 and the Part 16 sketch).

The warm-up builds the profile as a plain dict on the conversation brief
(`business_profile.py`). This module is the write-through to `pi_business_profiles`,
`pi_profile_facts` and `pi_page_snapshots`, and the other way round: what is stored (including an
edit, confirmation or deletion made in the dashboard) is read back into the brief before the next
turn, so the table is the truth.

Redaction (CLAUDE.md): every value is cleaned again on the way in (card, ID, phone, email) and
only roles are kept, never a third party's name. Only confirmed facts are grounded for the idea
filter (G2, OT13): `grounding_text`.
"""

import hashlib
import logging
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import business_profile
from app.modules.pi.business_profile_models import (
    PiBusinessProfile,
    PiPageSnapshot,
    PiProfileFact,
)
from app.shared.errors import BusinessRuleViolation, ResourceNotFound
from app.shared.scope import WorkspaceScope

log = logging.getLogger(__name__)

SNAPSHOT_FIELDS = ("site_name", "title", "description", "lang", "social_links", "orders_online")
_YEAR = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")


def _mine(model: Any, scope: WorkspaceScope) -> tuple[Any, ...]:
    return (model.tenant_id == scope.tenant_id, model.environment_id == scope.environment_id)


def _words(value: str) -> list[str]:
    return [w for w in re.split(r"[\s,;]+", value or "") if w]


def summary_from(facts: dict[str, str]) -> dict[str, Any]:
    """The profile row's own columns from the facts (spec `business_profile`)."""
    year = _YEAR.search(facts.get("since", ""))
    flags: dict[str, Any] = {}
    if facts.get("website") == "none":
        flags["website"] = "none"  # a fact, not a problem (16.5)
    if facts.get("online_orders"):
        flags["online_orders"] = facts["online_orders"]
    return {
        "display_name": facts.get("business_name", "")[:160],
        "what_they_do": facts.get("what_they_do", ""),
        "city_area": facts.get("places", "")[:160],
        "since_year": int(year.group(1)) if year else None,
        "size_band": facts.get("size", "")[:40],
        "channels": _words(facts.get("channels", "")),
        "website_url": facts.get("website_url", "")[:500],
        "social_urls": _words(facts.get("social_urls", "")),
        "digital_flags": flags,
        "language": facts.get("language", "")[:16],
    }


async def find(
    session: AsyncSession,
    scope: WorkspaceScope,
    customer_id: UUID,
    business_id: UUID | None = None,
) -> PiBusinessProfile | None:
    found: PiBusinessProfile | None = await session.scalar(
        select(PiBusinessProfile).where(
            *_mine(PiBusinessProfile, scope),
            PiBusinessProfile.customer_id == customer_id,
            PiBusinessProfile.business_id.is_(None)
            if business_id is None
            else PiBusinessProfile.business_id == business_id,
        )
    )
    return found


async def facts_of(
    session: AsyncSession, scope: WorkspaceScope, profile_id: UUID
) -> list[PiProfileFact]:
    return list(
        await session.scalars(
            select(PiProfileFact)
            .where(*_mine(PiProfileFact, scope), PiProfileFact.profile_id == profile_id)
            .order_by(PiProfileFact.created_at, PiProfileFact.key)
        )
    )


def as_dict(rows: list[PiProfileFact]) -> dict[str, Any]:
    """The stored facts in the shape `business_profile.py` works on."""
    return {
        "facts": [
            {
                "key": r.key,
                "value": r.value,
                "source": r.source,
                "confirmed": r.confirmed,
                "evidence": r.evidence_snippet,
                "url": r.source_url,
            }
            for r in rows
        ]
    }


async def load_dict(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID
) -> dict[str, Any] | None:
    profile = await find(session, scope, customer_id)
    if profile is None:
        return None
    return as_dict(await facts_of(session, scope, profile.id))


def grounding_text(rows: list[PiProfileFact]) -> str:
    """Words of the confirmed facts only, for the idea filter (G2). A page fact the owner has not
    confirmed contributes nothing (OT13)."""
    return business_profile.grounding_text(as_dict([r for r in rows if r.confirmed]))


async def refresh_summary(
    session: AsyncSession, scope: WorkspaceScope, profile: PiBusinessProfile
) -> None:
    rows = await facts_of(session, scope, profile.id)
    for column, value in summary_from({r.key: r.value for r in rows}).items():
        setattr(profile, column, value)


async def _upsert(
    session: AsyncSession,
    scope: WorkspaceScope,
    customer_id: UUID,
    profile_dict: dict[str, Any],
    look: dict[str, Any] | None,
) -> PiBusinessProfile:
    now = datetime.now(UTC)
    profile = await find(session, scope, customer_id)
    if profile is None:
        profile = PiBusinessProfile(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            customer_id=customer_id,
            channels=[],
            social_urls=[],
            digital_flags={},
        )
        session.add(profile)
        await session.flush()
    stored = {r.key: r for r in await facts_of(session, scope, profile.id)}
    for item in profile_dict.get("facts") or []:
        key, source = str(item.get("key")), str(item.get("source"))
        value = business_profile._clean(str(item.get("value") or ""))
        if key not in business_profile.KEYS or source not in business_profile.SOURCES or not value:
            continue
        confirmed = bool(item.get("confirmed"))
        evidence = business_profile._clean(str(item.get("evidence") or ""), 200)
        url = str(item.get("url") or "")[:500]
        row = stored.get(key)
        if row is None:
            session.add(
                PiProfileFact(
                    tenant_id=scope.tenant_id,
                    environment_id=scope.environment_id,
                    profile_id=profile.id,
                    key=key,
                    value=value,
                    source=source,
                    confirmed=confirmed,
                    confirmed_at=now if confirmed else None,
                    evidence_snippet=evidence,
                    source_url=url,
                    fetched_at=now if source != "owner" else None,
                )
            )
            continue
        if row.confirmed and source != business_profile.OWNER:
            continue  # a confirmed fact is not overwritten by a page or a photo
        if (row.value, row.source) != (value, source):
            row.value, row.source = value, source
            row.evidence_snippet, row.source_url = evidence, url
            row.fetched_at = now if source != "owner" else None
            row.confirmed, row.confirmed_at = confirmed, now if confirmed else None
        elif confirmed and not row.confirmed:
            row.confirmed, row.confirmed_at = True, now
    await session.flush()
    if isinstance(look, dict) and look.get("url"):
        extracted = {k: look[k] for k in SNAPSHOT_FIELDS if k in look}
        digest = (
            str(look.get("content_hash") or "")
            or hashlib.sha256(repr(sorted(extracted.items())).encode()).hexdigest()[:16]
        )
        session.add(
            PiPageSnapshot(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                profile_id=profile.id,
                url=str(look["url"])[:500],
                fetched_at=now,
                content_hash=digest[:64],
                extracted=extracted,
                status=str(look.get("status") or "ok")[:24],
            )
        )
        await session.flush()
    await refresh_summary(session, scope, profile)
    return profile


async def persist(
    session: AsyncSession,
    scope: WorkspaceScope,
    customer_id: UUID,
    profile_dict: dict[str, Any] | None,
    look: dict[str, Any] | None = None,
) -> PiBusinessProfile | None:
    """Write the warm-up's profile through to the tables. Never breaks the reply: a failure is
    logged and rolled back to a savepoint, and the brief still holds the profile."""
    if not profile_dict or not (profile_dict.get("facts") or look):
        return None
    try:
        async with session.begin_nested():
            return await _upsert(session, scope, customer_id, profile_dict, look)
    except Exception:  # noqa: BLE001 - write-through is best effort
        log.exception("business profile write-through failed")
        return None


async def sync_context(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: Any,
    context: dict[str, Any],
) -> None:
    """Before the turn: what is stored wins over the brief (the dashboard may have edited,
    confirmed or deleted a fact), and the confirmed facts become `profile_grounding` for G2."""
    try:  # the tables arrive with migration 0050: before it, the turn goes on without them
        async with session.begin_nested():
            profile = await find(session, scope, conversation.customer_id)
            rows = await facts_of(session, scope, profile.id) if profile is not None else []
    except Exception:  # noqa: BLE001
        log.warning("business profile tables not readable; continuing without them")
        return
    if profile is None:
        return
    brief = dict(conversation.service_brief or {})
    brief["business_profile"] = as_dict(rows)
    conversation.service_brief = brief
    if grounded := grounding_text(rows):
        context["profile_grounding"] = grounded


# --- dashboard edits ---------------------------------------------------------------------------


async def get_fact(
    session: AsyncSession, scope: WorkspaceScope, profile_id: UUID, fact_id: UUID
) -> PiProfileFact:
    row = await session.scalar(
        select(PiProfileFact).where(
            *_mine(PiProfileFact, scope),
            PiProfileFact.profile_id == profile_id,
            PiProfileFact.id == fact_id,
        )
    )
    if row is None:
        raise ResourceNotFound
    return row


async def confirm_fact(
    session: AsyncSession, scope: WorkspaceScope, profile_id: UUID, fact_id: UUID
) -> PiProfileFact:
    row = await get_fact(session, scope, profile_id, fact_id)
    if not row.confirmed:
        row.confirmed, row.confirmed_at = True, datetime.now(UTC)
    return row


async def _refresh(session: AsyncSession, scope: WorkspaceScope, profile_id: UUID) -> None:
    profile = await session.scalar(
        select(PiBusinessProfile).where(
            *_mine(PiBusinessProfile, scope), PiBusinessProfile.id == profile_id
        )
    )
    if profile is not None:
        await session.flush()
        await refresh_summary(session, scope, profile)


async def edit_fact(
    session: AsyncSession, scope: WorkspaceScope, profile_id: UUID, fact_id: UUID, value: str
) -> PiProfileFact:
    """A correction is the owner's own word: source owner, confirmed at once. Personal details
    are removed; a value that is nothing but that is refused."""
    row = await get_fact(session, scope, profile_id, fact_id)
    cleaned = business_profile._clean(value)
    if not cleaned:
        raise BusinessRuleViolation(
            "PROFILE_FACT_EMPTY", "The value is empty once personal details are removed", 422
        )
    row.value, row.source = cleaned, business_profile.OWNER
    row.confirmed, row.confirmed_at = True, datetime.now(UTC)
    row.evidence_snippet, row.source_url, row.fetched_at = "", "", None
    await _refresh(session, scope, profile_id)
    return row


async def delete_fact(
    session: AsyncSession, scope: WorkspaceScope, profile_id: UUID, fact_id: UUID
) -> None:
    await get_fact(session, scope, profile_id, fact_id)
    await session.execute(
        delete(PiProfileFact).where(*_mine(PiProfileFact, scope), PiProfileFact.id == fact_id)
    )
    await _refresh(session, scope, profile_id)


async def erase_for_customer(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID
) -> int:
    """Everything stored about this customer's business profile (R-PRIV-06). Returns the number
    of profiles removed."""
    ids = list(
        await session.scalars(
            select(PiBusinessProfile.id).where(
                *_mine(PiBusinessProfile, scope), PiBusinessProfile.customer_id == customer_id
            )
        )
    )
    if not ids:
        return 0
    await session.execute(
        delete(PiProfileFact).where(*_mine(PiProfileFact, scope), PiProfileFact.profile_id.in_(ids))
    )
    await session.execute(
        delete(PiPageSnapshot).where(
            *_mine(PiPageSnapshot, scope), PiPageSnapshot.profile_id.in_(ids)
        )
    )
    await session.execute(
        delete(PiBusinessProfile).where(
            *_mine(PiBusinessProfile, scope), PiBusinessProfile.id.in_(ids)
        )
    )
    return len(ids)
