"""Keeping personal data out of what pi stores and reads (pi Brain spec 6.3, R-PRIV-02).

`guard_inbound` takes card numbers, passwords and codes, ID and account numbers and a third party's
contact details out of an inbound message before the model or the log sees them. The original text
is kept encrypted for 30 days in `pi_quarantine` (when an encryption key is configured; without one
it is simply dropped). The reminder to the person is once per conversation per kind of data.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.integrations.crypto import CredentialManager
from app.integrations.errors import IntegrationError
from app.modules.pi import safety
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi.quarantine_models import RETENTION_DAYS, PiQuarantine
from app.shared.scope import WorkspaceScope


async def guard_inbound(
    session: AsyncSession,
    scope: WorkspaceScope,
    settings: Settings,
    conversation: PiConversation,
    message: PiMessage,
) -> dict[str, Any] | None:
    """Redact the message in place. Returns what the reply needs: the kinds found, the reminder to
    give (empty if already given), and whether nothing but the removed details was left."""
    original = message.body or ""
    found = safety.redact_pii(original)
    if not found.changed:
        return None
    manager = CredentialManager(settings)
    if manager.configured:
        try:
            session.add(
                PiQuarantine(
                    tenant_id=scope.tenant_id,
                    environment_id=scope.environment_id,
                    message_id=message.id,
                    kinds=[k.value for k in found.kinds],
                    payload=manager.encrypt(original),
                    expires_at=datetime.now(UTC) + timedelta(days=RETENTION_DAYS),
                )
            )
        except IntegrationError:
            pass  # never keep it if it cannot be kept encrypted
    message.body = found.text
    brief = dict(conversation.service_brief or {})
    notice, told = safety.pii_notice(
        found.kinds, list(brief.get("pii_told") or []), conversation.language
    )
    brief["pii_told"] = told
    conversation.service_brief = brief
    await session.flush()
    return {
        "kinds": [k.value for k in found.kinds],
        "notice": notice,
        "only": not safety.substantive(found.text),
    }


async def purge_expired(session: AsyncSession) -> int:
    """Delete quarantined originals older than their retention."""
    result = await session.execute(
        delete(PiQuarantine).where(PiQuarantine.expires_at < datetime.now(UTC))
    )
    return int(getattr(result, "rowcount", 0) or 0)
