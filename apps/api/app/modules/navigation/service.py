from collections.abc import Awaitable, Callable

from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.access.service import membership_grants
from app.modules.audit.service import record
from app.modules.environments.models import Environment
from app.modules.navigation.definitions import REGISTRY
from app.modules.navigation.models import NavigationPreference
from app.modules.navigation.registry import (
    NavContext,
    NavigationRegistry,
    ResolvedItem,
    Section,
    validate_custom_order,
)
from app.modules.products.service import enabled_products
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

BadgeProvider = Callable[[AsyncSession, WorkspaceScope], Awaitable[int | None]]
BADGES: dict[str, BadgeProvider] = {}


def badge_provider(key: str) -> Callable[[BadgeProvider], BadgeProvider]:
    def decorator(fn: BadgeProvider) -> BadgeProvider:
        BADGES[key] = fn
        return fn

    return decorator


class NavItemView(BaseModel):
    key: str
    label: str
    route: str
    icon: str
    type: str
    section: str
    sort_order: int
    badge: int | None
    analytics_id: str
    keywords: list[str]
    description: str
    children: list["NavItemView"]


class NavSectionView(BaseModel):
    key: str
    label: str
    customized: bool
    items: list[NavItemView]


class NavigationView(BaseModel):
    sections: list[NavSectionView]


SECTION_LABELS: dict[Section, str] = {"main": "Main", "admin": "Admin"}


class NavigationService:
    def __init__(
        self,
        session: AsyncSession,
        scope: WorkspaceScope,
        registry: NavigationRegistry = REGISTRY,
    ) -> None:
        self.session, self.scope, self.registry = session, scope, registry

    async def context(self) -> NavContext:
        roles: list[str] = []
        if self.scope.membership_id is not None:
            _, roles = await membership_grants(
                self.session, self.scope.tenant_id, self.scope.membership_id
            )
        kind = await self.session.scalar(
            select(Environment.kind).where(
                Environment.tenant_id == self.scope.tenant_id,
                Environment.id == self.scope.environment_id,
            )
        )
        return NavContext(
            permissions=self.scope.permissions,
            roles=frozenset(roles),
            products=await enabled_products(self.session, self.scope),
            environment_kind=kind or "production",
        )

    async def _preferences(self) -> dict[str, list[str]]:
        if self.scope.user_id is None:
            return {}
        rows = await self.session.scalars(
            select(NavigationPreference).where(
                NavigationPreference.tenant_id == self.scope.tenant_id,
                NavigationPreference.user_id == self.scope.user_id,
            )
        )
        return {r.section: [str(k) for k in r.item_order][:100] for r in rows}

    async def _view(self, item: ResolvedItem, badges: dict[str, int | None]) -> NavItemView:
        d = item.definition
        if d.badge and d.badge not in badges:
            provider = BADGES.get(d.badge)
            badges[d.badge] = await provider(self.session, self.scope) if provider else None
        return NavItemView(
            key=d.key,
            label=d.label,
            route=d.route,
            icon=d.icon,
            type=d.type,
            section=d.section,
            sort_order=d.sort_order,
            badge=badges.get(d.badge) if d.badge else None,
            analytics_id=d.analytics_id or f"nav.{d.key}",
            keywords=list(d.keywords),
            description=d.description,
            children=[await self._view(child, badges) for child in item.children],
        )

    async def resolve(self) -> NavigationView:
        preferences = await self._preferences()
        resolved = self.registry.resolve(await self.context(), preferences)
        badges: dict[str, int | None] = {}
        sections = []
        for section, items in resolved.items():
            sections.append(
                NavSectionView(
                    key=section,
                    label=SECTION_LABELS[section],
                    customized=bool(preferences.get(section)),
                    items=[await self._view(item, badges) for item in items],
                )
            )
        return NavigationView(sections=sections)

    async def save_order(self, section: Section, order: list[str]) -> NavigationView:
        if self.scope.user_id is None:
            raise BusinessRuleViolation("USER_REQUIRED", "Only people can customize navigation")
        context = await self.context()
        visible = [i for i in self.registry.top_level(section) if self.registry.allowed(i, context)]
        try:
            validated = validate_custom_order(visible, order)
        except ValueError:
            # Reordering can never make an inaccessible module visible.
            raise BusinessRuleViolation(
                "INVALID_NAVIGATION_ORDER", "The order contains unavailable items"
            ) from None
        await self.session.execute(
            insert(NavigationPreference)
            .values(
                tenant_id=self.scope.tenant_id,
                user_id=self.scope.user_id,
                section=section,
                item_order=validated,
            )
            .on_conflict_do_update(
                constraint="uq_navigation_preferences_entry", set_={"item_order": validated}
            )
        )
        await record(
            self.session,
            "navigation.order_saved",
            scope=self.scope,
            entity_type="navigation",
            details={"section": section, "order": validated},
            include_environment=False,
        )
        return await self.resolve()

    async def reset(self, section: Section) -> NavigationView:
        if self.scope.user_id is not None:
            await self.session.execute(
                delete(NavigationPreference).where(
                    NavigationPreference.tenant_id == self.scope.tenant_id,
                    NavigationPreference.user_id == self.scope.user_id,
                    NavigationPreference.section == section,
                )
            )
        return await self.resolve()
