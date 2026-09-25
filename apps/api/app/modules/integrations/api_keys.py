"""Environment-scoped API keys and the API-key authentication dependency.

Format: pk_live_<8 hex>_<43 url-safe chars> (pk_test_ for non-production environments).
Only SHA-256(full key) is stored; the public prefix (pk_live_xxxxxxxx) is the lookup key
and is globally unique. The secret is returned exactly once, at creation.

Scopes are permission keys and must be a subset of the creator's permissions at creation
time. At use time the effective permissions are key scopes ∩ the creator's *current*
grants, and the creator's membership, the tenant and the environment must still be
active — revoking a person also neuters their keys. A key can never manage keys.

`api_key_scope` yields a WorkspaceScope pinned to the key's tenant and environment, for
future public API routes. It never widens tenant/environment isolation: repositories use
the scope exactly as for session users.
"""

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.rate_limit import hit
from app.modules.access.permissions import ALL
from app.modules.access.service import membership_grants
from app.modules.audit.service import record
from app.modules.business_settings.capabilities import business_permissions
from app.modules.environments.models import Environment
from app.modules.integrations.models import ApiKey
from app.modules.integrations.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyView
from app.modules.memberships.models import Membership
from app.modules.tenants.models import Tenant
from app.shared.errors import BusinessRuleViolation, ResourceNotFound, Unauthenticated
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

KEY_FORMAT = re.compile(r"^(pk_(live|test)_[0-9a-f]{8})_([A-Za-z0-9_-]{43})$")
FORBIDDEN_SCOPES = frozenset({"api_keys.manage"})
TOUCH_INTERVAL = timedelta(minutes=1)


def now() -> datetime:
    return datetime.now(UTC)


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def parse_key(key: str) -> tuple[str, str] | None:
    match = KEY_FORMAT.fullmatch(key.strip())
    if match is None:
        return None
    return match.group(1), match.group(0)


def view(row: ApiKey) -> ApiKeyView:
    return ApiKeyView(
        id=row.id,
        name=row.name,
        prefix=row.prefix,
        scopes=list(row.scopes),
        created_at=row.created_at,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
        created_by_name=row.created_by_name,
    )


class ApiKeyService:
    def __init__(self, session: AsyncSession, scope: WorkspaceScope, max_keys: int = 50) -> None:
        self.session, self.scope, self.max_keys = session, scope, max_keys
        self.keys = WorkspaceRepository(session, ApiKey, scope)

    async def list(self) -> list[ApiKeyView]:
        rows = await self.session.scalars(
            self.keys.select().order_by(ApiKey.created_at.desc(), ApiKey.id).limit(200)
        )
        return [view(r) for r in rows]

    async def create(self, data: ApiKeyCreate) -> ApiKeyCreated:
        self.scope.require("api_keys.manage")
        scopes = sorted(set(data.scopes))
        if set(scopes) - ALL:
            raise BusinessRuleViolation("UNKNOWN_PERMISSION", "Unknown permission")
        if set(scopes) & FORBIDDEN_SCOPES:
            raise BusinessRuleViolation("PERMISSION_ESCALATION", "API keys cannot manage keys")
        if not set(scopes) <= self.scope.permissions:
            raise BusinessRuleViolation(
                "PERMISSION_ESCALATION", "A key cannot have access you do not have"
            )
        active = await self.session.scalar(
            select(func.count())
            .select_from(ApiKey)
            .where(self.keys.predicate(), ApiKey.revoked_at.is_(None))
        )
        if int(active or 0) >= self.max_keys:
            raise BusinessRuleViolation("LIMIT_REACHED", "API key limit reached")
        kind = await self.session.scalar(
            select(Environment.kind).where(
                Environment.tenant_id == self.scope.tenant_id,
                Environment.id == self.scope.environment_id,
            )
        )
        label = "live" if kind == "production" else "test"
        expires = now() + timedelta(days=data.expires_in_days) if data.expires_in_days else None
        for _ in range(5):
            prefix = f"pk_{label}_{secrets.token_hex(4)}"
            secret = secrets.token_urlsafe(32)
            full = f"{prefix}_{secret}"
            row = self.keys.new(
                name=data.name,
                prefix=prefix,
                secret_hash=key_hash(full),
                scopes=scopes,
                expires_at=expires,
                created_by_user_id=self.scope.user_id,
                created_by_membership_id=self.scope.membership_id,
                created_by_name=self.scope.actor_label[:160],
            )
            try:
                async with self.session.begin_nested():
                    await self.keys.add(row)
            except IntegrityError:
                continue  # prefix collision (2^32 space): try again
            await record(
                self.session,
                "api_key.created",
                scope=self.scope,
                entity_type="api_key",
                entity_id=row.id,
                details={
                    "prefix": prefix,
                    "scopes": scopes,
                    "expires_in_days": data.expires_in_days,
                },
            )
            return ApiKeyCreated(**view(row).model_dump(), secret=full)
        raise BusinessRuleViolation("KEY_GENERATION_FAILED", "Could not create a key; retry", 503)

    async def revoke(self, key_id: UUID) -> None:
        self.scope.require("api_keys.manage")
        row = await self.keys.get(key_id, for_update=True)
        if row.revoked_at is None:
            row.revoked_at = now()
            await self.session.flush()
            await record(
                self.session,
                "api_key.revoked",
                scope=self.scope,
                entity_type="api_key",
                entity_id=row.id,
                details={"prefix": row.prefix},
            )


def _presented_key(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.headers.get("x-api-key")


async def authenticate(session: AsyncSession, presented: str) -> WorkspaceScope:
    parsed = parse_key(presented)
    if parsed is None:
        raise Unauthenticated
    prefix, full = parsed
    row = await session.scalar(select(ApiKey).where(ApiKey.prefix == prefix))
    # Constant-time comparison; unknown prefixes compare against a dummy digest.
    expected = row.secret_hash if row is not None else "0" * 64
    if not hmac.compare_digest(expected, key_hash(full)) or row is None:
        raise Unauthenticated
    current = now()
    if row.revoked_at is not None or (row.expires_at is not None and row.expires_at <= current):
        raise Unauthenticated
    active = await session.scalar(
        select(Environment.id)
        .join(Tenant, Tenant.id == Environment.tenant_id)
        .where(
            Environment.tenant_id == row.tenant_id,
            Environment.id == row.environment_id,
            Environment.status == "active",
            Tenant.status == "active",
        )
    )
    if active is None:
        raise Unauthenticated
    granted = frozenset(row.scopes)
    if row.created_by_membership_id is not None:
        membership = await session.scalar(
            select(Membership.id).where(
                Membership.id == row.created_by_membership_id,
                Membership.tenant_id == row.tenant_id,
                Membership.status == "active",
            )
        )
        if membership is None:
            raise Unauthenticated
        current_grants, _roles = await membership_grants(
            session, row.tenant_id, row.created_by_membership_id
        )
        granted &= current_grants
    granted = await business_permissions(session, row.tenant_id, row.environment_id, granted)
    granted -= FORBIDDEN_SCOPES
    if row.last_used_at is None or row.last_used_at < current - TOUCH_INTERVAL:
        await session.execute(
            update(ApiKey).where(ApiKey.id == row.id).values(last_used_at=current)
        )
        await session.commit()
    return WorkspaceScope.system(
        row.tenant_id, row.environment_id, frozenset(granted), f"api_key:{prefix}"
    )


async def api_key_scope(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> WorkspaceScope:
    """Dependency for public API routes authenticated by API key (no cookies/CSRF)."""
    presented = _presented_key(request)
    if not presented or len(presented) > 128:
        raise Unauthenticated
    parsed = parse_key(presented)
    if parsed and not await hit(request, "api_key", parsed[0], 600, 60):
        raise BusinessRuleViolation("RATE_LIMITED", "Too many requests", 429)
    scope = await authenticate(session, presented)
    request_id = getattr(request.state, "request_id", None)
    return WorkspaceScope.system(
        scope.tenant_id,
        scope.environment_id,
        scope.permissions,
        scope.actor_label,
        request_id=request_id,
    )


ApiKeyScope = Annotated[WorkspaceScope, Depends(api_key_scope)]


def require_api_scope(*permissions: str):  # type: ignore[no-untyped-def]
    async def dependency(scope: ApiKeyScope) -> WorkspaceScope:
        scope.require(*permissions)
        return scope

    return dependency


__all__ = ["ApiKeyScope", "ApiKeyService", "ResourceNotFound", "api_key_scope", "authenticate"]
