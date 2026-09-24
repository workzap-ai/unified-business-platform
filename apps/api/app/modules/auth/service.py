from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.audit.service import record
from app.modules.auth.crypto import digest, hash_password, needs_rehash, new_token, verify_password
from app.modules.auth.models import AuthSession, UserCredential
from app.modules.auth.schemas import RegisterRequest
from app.modules.branches.models import Branch
from app.modules.environments.models import Environment
from app.modules.memberships.models import Membership
from app.modules.tenants.context import active_memberships
from app.modules.tenants.models import Tenant
from app.modules.tenants.onboarding import provision_tenant
from app.modules.users.models import PlatformUser
from app.shared.errors import BusinessRuleViolation, Conflict, ResourceNotFound, Unauthenticated

TOUCH_INTERVAL = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class IssuedSession:
    record: AuthSession
    token: str
    csrf: str


@dataclass(frozen=True, slots=True)
class AuthContext:
    session: AuthSession
    user: PlatformUser


def now() -> datetime:
    return datetime.now(UTC)


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session, self.settings = session, settings

    async def _issue(self, user: PlatformUser, user_agent: str) -> IssuedSession:
        token, csrf = new_token(), new_token()
        current = now()
        auth = AuthSession(
            user_id=user.id,
            token_hash=digest(token),
            csrf_hash=digest(csrf),
            expires_at=current + timedelta(hours=self.settings.session_ttl_hours),
            last_seen_at=current,
            user_agent=user_agent[:200],
        )
        await self._default_workspace(auth)
        self.session.add(auth)
        await self.session.flush()
        return IssuedSession(auth, token, csrf)

    async def _default_workspace(self, auth: AuthSession) -> None:
        membership = await self.session.scalar(
            active_memberships(auth.user_id).order_by(Membership.created_at).limit(1)
        )
        if membership is None:
            return
        environment = await self.session.scalar(
            select(Environment).where(
                Environment.tenant_id == membership.tenant_id,
                Environment.is_default.is_(True),
                Environment.status == "active",
            )
        )
        auth.active_tenant_id = membership.tenant_id
        auth.active_environment_id = environment.id if environment else None
        auth.active_branch_id = None

    async def register(self, data: RegisterRequest, user_agent: str) -> IssuedSession:
        if not self.settings.allow_registration:
            raise BusinessRuleViolation("REGISTRATION_DISABLED", "Registration is not available")
        try:
            async with self.session.begin_nested():
                user = PlatformUser(email=data.email, display_name=data.display_name)
                self.session.add(user)
                await self.session.flush()
        except IntegrityError:
            # Same public outcome as other validation conflicts; no account enumeration detail.
            raise Conflict("Registration could not be completed") from None
        self.session.add(
            UserCredential(
                user_id=user.id,
                password_hash=hash_password(data.password),
                password_changed_at=now(),
            )
        )
        await provision_tenant(self.session, user, data.organization_name)
        issued = await self._issue(user, user_agent)
        await record(
            self.session,
            "auth.registered",
            actor_user_id=user.id,
            tenant_id=issued.record.active_tenant_id,
            entity_type="user",
            entity_id=user.id,
        )
        return issued

    async def login(self, email: str, password: str, user_agent: str) -> IssuedSession:
        row = (
            await self.session.execute(
                select(PlatformUser, UserCredential)
                .join(UserCredential, UserCredential.user_id == PlatformUser.id)
                .where(PlatformUser.email == email)
                .with_for_update(of=UserCredential)
            )
        ).first()
        user, credential = (row[0], row[1]) if row else (None, None)
        current = now()
        if credential is not None and credential.locked_until and credential.locked_until > current:
            verify_password(None, password)  # constant-ish timing for locked accounts
            await self._failed(user, "locked")
            raise Unauthenticated
        valid = verify_password(credential.password_hash if credential else None, password)
        if not valid or user is None or credential is None or user.status != "active":
            if credential is not None:
                credential.failed_attempts += 1
                if credential.failed_attempts >= self.settings.login_max_failures:
                    credential.locked_until = current + timedelta(
                        minutes=self.settings.login_lockout_minutes
                    )
                    credential.failed_attempts = 0
            await self._failed(user, "invalid")
            raise Unauthenticated
        credential.failed_attempts = 0
        credential.locked_until = None
        if needs_rehash(credential.password_hash):
            credential.password_hash = hash_password(password)
        issued = await self._issue(user, user_agent)
        await record(self.session, "auth.login", actor_user_id=user.id, entity_type="user")
        return issued

    async def _failed(self, user: PlatformUser | None, reason: str) -> None:
        await record(
            self.session,
            "auth.login_failed",
            actor_user_id=None,
            entity_type="user",
            entity_id=user.id if user else None,
            outcome="denied",
            details={"reason": reason},
        )

    async def resolve(self, token: str) -> AuthContext:
        row = (
            await self.session.execute(
                select(AuthSession, PlatformUser)
                .join(PlatformUser, PlatformUser.id == AuthSession.user_id)
                .where(
                    AuthSession.token_hash == digest(token),
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > now(),
                    PlatformUser.status == "active",
                )
            )
        ).first()
        if row is None:
            raise Unauthenticated
        auth, user = row[0], row[1]
        if now() - auth.last_seen_at > TOUCH_INTERVAL:
            await self.session.execute(
                update(AuthSession).where(AuthSession.id == auth.id).values(last_seen_at=now())
            )
            await self.session.commit()
        return AuthContext(auth, user)

    async def logout(self, auth: AuthSession) -> None:
        await self.session.execute(
            update(AuthSession)
            .where(AuthSession.id == auth.id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now())
        )
        await record(self.session, "auth.logout", actor_user_id=auth.user_id)

    async def logout_all(self, user_id: UUID) -> None:
        await self.session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now())
        )
        await record(self.session, "auth.logout_all", actor_user_id=user_id)

    async def change_password(
        self, auth: AuthSession, current_password: str, new_password: str
    ) -> None:
        credential = await self.session.scalar(
            select(UserCredential).where(UserCredential.user_id == auth.user_id).with_for_update()
        )
        if credential is None or not verify_password(credential.password_hash, current_password):
            await record(
                self.session,
                "auth.password_change_failed",
                actor_user_id=auth.user_id,
                outcome="denied",
            )
            raise BusinessRuleViolation("INVALID_CREDENTIALS", "Current password is incorrect")
        credential.password_hash = hash_password(new_password)
        credential.password_changed_at = now()
        # Revoke every other session; the current one stays signed in.
        await self.session.execute(
            update(AuthSession)
            .where(
                AuthSession.user_id == auth.user_id,
                AuthSession.id != auth.id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=now())
        )
        await record(self.session, "auth.password_changed", actor_user_id=auth.user_id)

    async def select_workspace(
        self,
        auth: AuthSession,
        tenant_id: UUID,
        environment_id: UUID | None,
        branch_id: UUID | None,
    ) -> None:
        membership = await self.session.scalar(
            active_memberships(auth.user_id).where(Membership.tenant_id == tenant_id)
        )
        if membership is None:
            raise ResourceNotFound
        env_query = select(Environment).where(
            Environment.tenant_id == tenant_id, Environment.status == "active"
        )
        env_query = (
            env_query.where(Environment.id == environment_id)
            if environment_id
            else env_query.where(Environment.is_default.is_(True))
        )
        environment = await self.session.scalar(env_query)
        if environment is None:
            raise ResourceNotFound
        if branch_id is not None:
            branch = await self.session.scalar(
                select(Branch.id).where(Branch.tenant_id == tenant_id, Branch.id == branch_id)
            )
            if branch is None:
                raise ResourceNotFound
        await self.session.execute(
            update(AuthSession)
            .where(AuthSession.id == auth.id)
            .values(
                active_tenant_id=tenant_id,
                active_environment_id=environment.id,
                active_branch_id=branch_id,
            )
        )
        auth.active_tenant_id, auth.active_environment_id = tenant_id, environment.id
        auth.active_branch_id = branch_id

    async def tenant(self, tenant_id: UUID | None) -> Tenant | None:
        if tenant_id is None:
            return None
        return await self.session.get(Tenant, tenant_id)
