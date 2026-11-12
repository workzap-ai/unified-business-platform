"""Idempotency keys, replay keys, the rate-limit count and the audit trail (one table)."""

import hashlib
import random
from uuid import UUID

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi_saas.nori_credits.models import PiNoriBridgeLog
from app.modules.pi_saas.nori_credits.resilience import digits, mask_number

REPLAY_RETENTION = "24 hours"
INBOUND_RETENTION = "7 days"
AUDIT_RETENTION = "90 days"


def key_of(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def number_hash(number: object) -> str:
    return hashlib.sha256(f"nori-bridge:{digits(number)}".encode()).hexdigest()


async def claim(
    session: AsyncSession,
    kind: str,
    key: str,
    *,
    outcome: str = "claimed",
    tenant_id: UUID | None = None,
    environment_id: UUID | None = None,
) -> bool:
    """Insert the key; False when it was already there (a retry or a replay)."""
    statement = (
        insert(PiNoriBridgeLog)
        .values(
            kind=kind,
            dedupe_key=key,
            outcome=outcome,
            tenant_id=tenant_id,
            environment_id=environment_id,
        )
        .on_conflict_do_nothing(
            index_elements=["kind", "dedupe_key"], index_where=text("dedupe_key IS NOT NULL")
        )
        .returning(PiNoriBridgeLog.id)
    )
    return (await session.scalar(statement)) is not None


async def outcome_of(session: AsyncSession, kind: str, key: str) -> str | None:
    found: str | None = await session.scalar(
        select(PiNoriBridgeLog.outcome).where(
            PiNoriBridgeLog.kind == kind, PiNoriBridgeLog.dedupe_key == key
        )
    )
    return found


async def set_outcome(
    session: AsyncSession, kind: str, key: str, outcome: str, reason: str = ""
) -> None:
    await session.execute(
        update(PiNoriBridgeLog)
        .where(PiNoriBridgeLog.kind == kind, PiNoriBridgeLog.dedupe_key == key)
        .values(outcome=outcome[:40], reason=reason[:80])
    )


async def audit(
    session: AsyncSession,
    kind: str,
    outcome: str,
    *,
    reason: str = "",
    number: object = "",
    tenant_id: UUID | None = None,
    environment_id: UUID | None = None,
) -> None:
    """One audit row: who (masked number and a hash), when (created_at), outcome. Never a body."""
    await session.execute(
        insert(PiNoriBridgeLog).values(
            kind=kind,
            outcome=outcome[:40],
            reason=reason[:80],
            recipient_mask=mask_number(number) if number else "",
            recipient_hash=number_hash(number) if number else "",
            tenant_id=tenant_id,
            environment_id=environment_id,
        )
    )


async def sends_in_last_minute(session: AsyncSession) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(PiNoriBridgeLog)
        .where(
            PiNoriBridgeLog.kind == "send",
            PiNoriBridgeLog.dedupe_key.is_(None),
            PiNoriBridgeLog.outcome != "rate_limited",
            PiNoriBridgeLog.created_at > func.now() - text("interval '1 minute'"),
        )
    )
    return int(count or 0)


async def purge(session: AsyncSession, *, chance: float = 0.02) -> None:
    """Drop expired keys and old audit rows on a small share of calls (no scheduled job needed)."""
    if random.random() > chance:
        return
    for kind, age in (
        ("replay", REPLAY_RETENTION),
        ("inbound", INBOUND_RETENTION),
        ("send", AUDIT_RETENTION),
        ("board", AUDIT_RETENTION),
    ):
        await session.execute(
            delete(PiNoriBridgeLog).where(
                PiNoriBridgeLog.kind == kind,
                PiNoriBridgeLog.created_at < func.now() - text(f"interval '{age}'"),
            )
        )
