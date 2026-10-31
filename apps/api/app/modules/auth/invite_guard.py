"""Containment for invitations sent to an address whose owner never proved it.

Anyone can register any email address and is signed in at once, and the mailbox is
not checked before sign-in. If an admin later invites that address, attaching the
roles to the existing account would hand them to whoever registered first. So an
account whose email is unverified is treated as a brand-new invitee: its credential
is replaced by a random one nobody knows (the squatter's password stops working),
its live sessions are revoked, and only the emailed set-password link, which proves
the mailbox, gets anyone back in. Verified accounts are left exactly as they are."""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.service import record
from app.modules.auth.crypto import hash_password, new_token
from app.modules.auth.models import AuthSession, UserCredential
from app.modules.users.models import PlatformUser


async def revoke_sessions(session: AsyncSession, user_id: object) -> None:
    await session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def contain_unverified_account(session: AsyncSession, user: PlatformUser) -> bool:
    """True when the account was unverified and has been reset; the caller must then
    send the set-password invitation link instead of a plain sign-in link."""
    if user.email_verified_at is not None:
        return False
    current = datetime.now(UTC)
    credential = await session.scalar(
        select(UserCredential).where(UserCredential.user_id == user.id).with_for_update()
    )
    # Random and never revealed, exactly like a brand-new invitee's placeholder.
    placeholder = hash_password(new_token())
    if credential is None:
        session.add(
            UserCredential(user_id=user.id, password_hash=placeholder, password_changed_at=current)
        )
    else:
        credential.password_hash = placeholder
        credential.password_changed_at = current
        credential.failed_attempts = 0
        credential.locked_until = None
    await revoke_sessions(session, user.id)
    await record(
        session,
        "auth.unverified_account_invited_reset",
        actor_user_id=user.id,
        entity_type="user",
        entity_id=user.id,
    )
    return True
