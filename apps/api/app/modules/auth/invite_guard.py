"""Invitations to an email address nobody has proved they own (SEC-1).

Anyone can register any address and is signed in at once; the mailbox is never checked
first. So when an admin invites an address whose account has no verified email, the
account is NOT handed the roles and its credential is NOT touched:

* the membership is created as pending (status "revoked", which grants nothing anywhere,
  plus a live invitation token for that workspace);
* the set-password link goes only to the mailbox, and is never returned in an API
  response or written to a log, so no admin can use it;
* only following the emailed link activates the pending memberships, and that proves the
  mailbox, so everything the previous holder had (password, sessions, passkeys, faces,
  PIN, half-finished second steps) is cut off in `accept_invite`.

Accounts with a verified email keep the plain "sign in" behaviour. No new column or
status value is needed."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.crypto import digest, hash_password, new_token
from app.modules.auth.models import (
    AuthSession,
    MemberInviteToken,
    UserCredential,
    UserFace,
    UserPasskey,
)
from app.modules.memberships.models import Membership
from app.modules.users.models import PlatformUser


def needs_proof(user: PlatformUser) -> bool:
    return user.email_verified_at is None


async def burn_hash() -> None:
    """Same Argon2 work whichever kind of account was invited, so timing does not tell
    a new, an unverified and a verified address apart."""
    hash_password(new_token())


async def issue_invite_token(
    session: AsyncSession, user_id: UUID, tenant_id: UUID, ttl_minutes: int
) -> str:
    """A fresh one-time token for this person and workspace; older ones stop working."""
    current = datetime.now(UTC)
    await session.execute(
        update(MemberInviteToken)
        .where(
            MemberInviteToken.user_id == user_id,
            MemberInviteToken.tenant_id == tenant_id,
            MemberInviteToken.used_at.is_(None),
        )
        .values(used_at=current)
    )
    token = new_token()
    session.add(
        MemberInviteToken(
            user_id=user_id,
            tenant_id=tenant_id,
            token_hash=digest(token),
            expires_at=current + timedelta(minutes=ttl_minutes),
        )
    )
    return token


async def withdraw_invites(session: AsyncSession, user_id: UUID, tenant_id: UUID) -> None:
    """A removed member's (or an admin-cancelled pending invite's) links stop working."""
    await session.execute(
        update(MemberInviteToken)
        .where(
            MemberInviteToken.user_id == user_id,
            MemberInviteToken.tenant_id == tenant_id,
            MemberInviteToken.used_at.is_(None),
        )
        .values(used_at=datetime.now(UTC))
    )


async def revoke_sessions(session: AsyncSession, user_id: UUID) -> None:
    await session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def cut_off_previous_holder(session: AsyncSession, credential: UserCredential) -> None:
    """The mailbox owner has just proved the mailbox: nothing the account's earlier
    holder enrolled may survive. (Half-finished second steps die with the password
    change: see mfa._success.)"""
    user_id = credential.user_id
    await session.execute(delete(UserPasskey).where(UserPasskey.user_id == user_id))
    await session.execute(delete(UserFace).where(UserFace.user_id == user_id))
    await session.execute(
        update(UserCredential)
        .where(UserCredential.user_id == user_id)
        .values(
            second_factor_pin_hash=None,
            second_factor_failures=0,
            second_factor_locked_until=None,
        )
    )


async def activate_pending(session: AsyncSession, user_id: UUID, current: datetime) -> None:
    """Switch on the pending memberships of every live invitation this person holds."""
    tokens = (
        await session.scalars(
            select(MemberInviteToken).where(
                MemberInviteToken.user_id == user_id,
                MemberInviteToken.used_at.is_(None),
                MemberInviteToken.expires_at > current,
            )
        )
    ).all()
    for token in tokens:
        token.used_at = current
        await session.execute(
            update(Membership)
            .where(
                Membership.tenant_id == token.tenant_id,
                Membership.user_id == user_id,
                Membership.status == "revoked",
            )
            .values(status="active")
        )
