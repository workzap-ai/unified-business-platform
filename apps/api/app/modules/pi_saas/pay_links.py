"""Token-based access to a payment row without a session: issue, resolve, invalidate.

Follows the exact pattern already used for password reset / email verification
(``app/modules/auth/crypto.py``): the raw token is a ``secrets.token_urlsafe(32)``
value shown exactly once (in the link/QR); only its SHA-256 digest is ever stored, and
a constant-time-safe digest lookup is the only way back to the row. There is no
sequential or guessable id involved anywhere in this flow.

Generic over the two row types that carry a pay-link (``PiManualPayment`` and
``PiPaymentRequest``): they do not share a base class beyond ``TenantRow``/
``WorkspaceRow``, so this reads/writes ``link_token_hash`` / ``link_expires_at`` /
``status`` on whatever is passed in (a small structural — i.e. duck-typed — contract)
rather than importing either concrete model.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.crypto import digest, new_token

LINK_TTL = timedelta(days=7)


@runtime_checkable
class PayLinkRow(Protocol):
    link_token_hash: str | None
    link_expires_at: datetime | None
    status: str


def issue[T: PayLinkRow](row: T) -> str:
    """Set a fresh token (silently replacing any previous one) and return the raw
    value. The caller must commit; nothing else can recover this value afterwards."""
    token = new_token()
    row.link_token_hash = digest(token)
    row.link_expires_at = datetime.now(UTC) + LINK_TTL
    return token


def invalidate(row: PayLinkRow) -> None:
    """Make the current link permanently unusable (e.g. once the row reaches a
    terminal state outside the normal review flow)."""
    row.link_token_hash = None
    row.link_expires_at = None


async def resolve[T: PayLinkRow](
    session: AsyncSession,
    model: type[T],
    token: str,
    *,
    live_statuses: frozenset[str],
    lock: bool = False,
) -> T | None:
    """Digest lookup plus an expiry and terminal-state check, all in one generic 404
    shape: any failure (wrong token, expired, already in a terminal state) returns
    ``None`` so the caller can answer with one indistinguishable 404."""
    query = select(model).where(model.link_token_hash == digest(token))  # type: ignore[arg-type]
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = await session.scalar(query)
    if row is None:
        return None
    if row.link_expires_at is None or row.link_expires_at <= datetime.now(UTC):
        return None
    if row.status not in live_statuses:
        return None
    return row
