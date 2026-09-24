from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.service import record
from app.modules.products.models import (
    EnvironmentProductInstallation,
    PlatformProduct,
    TenantProductInstallation,
)
from app.modules.products.registry import PRODUCTS
from app.shared.errors import BusinessRuleViolation, ResourceNotFound
from app.shared.scope import WorkspaceScope


class ProductState(BaseModel):
    key: str
    name: str
    description: str
    category: str
    features: list[str]
    tenant_status: str | None  # installed | suspended | None (not installed)
    environment_enabled: bool
    enabled_features: list[str]
    installed_at: datetime | None


async def sync_products(session: AsyncSession) -> None:
    """Insert catalog rows for registered products that the database does not have yet."""
    for product in PRODUCTS.all():
        await session.execute(
            insert(PlatformProduct)
            .values(
                key=product.key,
                name=product.name,
                description=product.description,
                category=product.category,
                features=list(product.features),
            )
            .on_conflict_do_nothing(index_elements=["key"])
        )


async def enabled_products(session: AsyncSession, scope: WorkspaceScope) -> dict[str, set[str]]:
    """Product key -> enabled features for this tenant environment (entitlement check)."""
    rows = await session.execute(
        select(PlatformProduct.key, PlatformProduct.features, EnvironmentProductInstallation)
        .join(TenantProductInstallation, TenantProductInstallation.product_id == PlatformProduct.id)
        .join(
            EnvironmentProductInstallation,
            (EnvironmentProductInstallation.installation_id == TenantProductInstallation.id)
            & (EnvironmentProductInstallation.tenant_id == TenantProductInstallation.tenant_id),
        )
        .where(
            TenantProductInstallation.tenant_id == scope.tenant_id,
            TenantProductInstallation.status == "installed",
            EnvironmentProductInstallation.environment_id == scope.environment_id,
            EnvironmentProductInstallation.enabled.is_(True),
            PlatformProduct.status == "available",
        )
    )
    return {
        key: set(features) - set(env_install.disabled_features)
        for key, features, env_install in rows
    }


async def product_enabled(session: AsyncSession, scope: WorkspaceScope, key: str) -> bool:
    return key in await enabled_products(session, scope)


class ProductService:
    def __init__(self, session: AsyncSession, scope: WorkspaceScope) -> None:
        self.session, self.scope = session, scope

    async def states(self) -> list[ProductState]:
        rows = await self.session.execute(
            select(PlatformProduct, TenantProductInstallation, EnvironmentProductInstallation)
            .outerjoin(
                TenantProductInstallation,
                (TenantProductInstallation.product_id == PlatformProduct.id)
                & (TenantProductInstallation.tenant_id == self.scope.tenant_id),
            )
            .outerjoin(
                EnvironmentProductInstallation,
                (EnvironmentProductInstallation.installation_id == TenantProductInstallation.id)
                & (EnvironmentProductInstallation.tenant_id == self.scope.tenant_id)
                & (EnvironmentProductInstallation.environment_id == self.scope.environment_id),
            )
            .where(PlatformProduct.status == "available")
            .order_by(PlatformProduct.name)
        )
        result = []
        for product, tenant_install, env_install in rows:
            enabled = bool(
                tenant_install
                and tenant_install.status == "installed"
                and env_install
                and env_install.enabled
            )
            disabled = set(env_install.disabled_features) if env_install else set()
            result.append(
                ProductState(
                    key=product.key,
                    name=product.name,
                    description=product.description,
                    category=product.category,
                    features=list(product.features),
                    tenant_status=tenant_install.status if tenant_install else None,
                    environment_enabled=enabled,
                    enabled_features=sorted(set(product.features) - disabled) if enabled else [],
                    installed_at=tenant_install.installed_at if tenant_install else None,
                )
            )
        return result

    async def _product(self, key: str) -> PlatformProduct:
        product = await self.session.scalar(
            select(PlatformProduct).where(
                PlatformProduct.key == key, PlatformProduct.status == "available"
            )
        )
        if product is None or PRODUCTS.get(key) is None:
            raise ResourceNotFound
        return product

    async def install(self, key: str) -> None:
        """Install for the tenant and enable in the current environment (idempotent)."""
        self.scope.require("admin.products.manage")
        product = await self._product(key)
        await self.session.execute(
            insert(TenantProductInstallation)
            .values(
                tenant_id=self.scope.tenant_id,
                product_id=product.id,
                installed_by_user_id=self.scope.user_id,
                installed_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(constraint="uq_tenant_product_installations_product")
        )
        installation = await self.session.scalar(
            select(TenantProductInstallation)
            .where(
                TenantProductInstallation.tenant_id == self.scope.tenant_id,
                TenantProductInstallation.product_id == product.id,
            )
            .with_for_update()
        )
        assert installation is not None
        installation.status = "installed"
        await self.session.execute(
            insert(EnvironmentProductInstallation)
            .values(
                tenant_id=self.scope.tenant_id,
                environment_id=self.scope.environment_id,
                installation_id=installation.id,
            )
            .on_conflict_do_update(
                constraint="uq_environment_product_installations_entry", set_={"enabled": True}
            )
        )
        await self.session.flush()
        definition = PRODUCTS.get(key)
        assert definition is not None
        for hook in definition.install_hooks:
            await hook(self.session, self.scope)
        await record(
            self.session,
            "product.installed",
            scope=self.scope,
            entity_type="platform_product",
            entity_id=product.id,
            details={"product": key},
        )

    async def set_enabled(self, key: str, enabled: bool) -> None:
        self.scope.require("admin.products.manage")
        product = await self._product(key)
        installation = await self.session.scalar(
            select(TenantProductInstallation).where(
                TenantProductInstallation.tenant_id == self.scope.tenant_id,
                TenantProductInstallation.product_id == product.id,
            )
        )
        if installation is None:
            raise BusinessRuleViolation("NOT_INSTALLED", "Install this product first")
        if enabled:
            await self.install(key)
            return
        env_install = await self.session.scalar(
            select(EnvironmentProductInstallation).where(
                EnvironmentProductInstallation.tenant_id == self.scope.tenant_id,
                EnvironmentProductInstallation.environment_id == self.scope.environment_id,
                EnvironmentProductInstallation.installation_id == installation.id,
            )
        )
        if env_install is not None:
            env_install.enabled = False
            await self.session.flush()
        await record(
            self.session,
            "product.disabled",
            scope=self.scope,
            entity_type="platform_product",
            entity_id=product.id,
            details={"product": key},
        )

    async def installation_id(self, key: str) -> UUID | None:
        found: UUID | None = await self.session.scalar(
            select(TenantProductInstallation.id)
            .join(PlatformProduct, PlatformProduct.id == TenantProductInstallation.product_id)
            .where(
                TenantProductInstallation.tenant_id == self.scope.tenant_id,
                PlatformProduct.key == key,
            )
        )
        return found
