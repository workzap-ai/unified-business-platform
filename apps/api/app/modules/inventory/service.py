from collections.abc import Sequence
from datetime import date
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, Pagination
from app.modules.audit.service import record
from app.modules.business_settings.service import get_settings_row
from app.modules.catalog.models import CatalogProduct, CatalogVariant
from app.modules.inventory.models import InventoryLocation, StockLevel, StockMovement
from app.modules.inventory.schemas import (
    Availability,
    LocationCreate,
    MovementView,
    StockAdjustment,
    StockLevelView,
)
from app.modules.notifications.service import notify
from app.shared.errors import BusinessRuleViolation, Conflict, ResourceNotFound
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository, like_pattern, to_page


class InventoryService:
    def __init__(self, session: AsyncSession, scope: WorkspaceScope) -> None:
        self.session, self.scope = session, scope
        self.locations = WorkspaceRepository(session, InventoryLocation, scope)
        self.levels = WorkspaceRepository(session, StockLevel, scope)
        self.movements = WorkspaceRepository(session, StockMovement, scope)
        self.variants = WorkspaceRepository(session, CatalogVariant, scope)
        self.products = WorkspaceRepository(session, CatalogProduct, scope)

    # Locations ------------------------------------------------------------------
    async def default_location(self) -> InventoryLocation:
        found = await self.locations.find(InventoryLocation.is_default.is_(True))
        if found is not None:
            return found
        await self.session.execute(
            insert(InventoryLocation)
            .values(
                tenant_id=self.scope.tenant_id,
                environment_id=self.scope.environment_id,
                name="Main location",
                code="main",
                is_default=True,
            )
            .on_conflict_do_nothing()
        )
        found = await self.locations.find(InventoryLocation.is_default.is_(True))
        if found is None:
            raise Conflict("Default location could not be created")
        return found

    async def list_locations(self) -> list[InventoryLocation]:
        await self.default_location()
        rows = await self.session.scalars(
            self.locations.select()
            .order_by(InventoryLocation.is_default.desc(), InventoryLocation.name)
            .limit(200)
        )
        return list(rows)

    async def create_location(self, data: LocationCreate) -> InventoryLocation:
        self.scope.require("inventory.adjust")
        await self.default_location()
        try:
            async with self.session.begin_nested():
                row = await self.locations.add(self.locations.new(**data.model_dump()))
        except IntegrityError:
            raise Conflict("A location with this code already exists") from None
        await record(
            self.session,
            "inventory.location_created",
            scope=self.scope,
            entity_type="inventory_location",
            entity_id=row.id,
        )
        return row

    # Levels and availability ----------------------------------------------------------
    async def list_levels(
        self,
        page: Pagination,
        search: str | None = None,
        location_id: UUID | None = None,
        low_only: bool = False,
    ) -> Page[StockLevelView]:
        settings = await get_settings_row(self.session, self.scope)
        threshold = func.coalesce(CatalogVariant.low_stock_threshold, settings.low_stock_threshold)
        available = StockLevel.on_hand - StockLevel.reserved
        statement = (
            select(StockLevel, CatalogVariant, CatalogProduct, InventoryLocation)
            .join(
                CatalogVariant,
                and_(
                    CatalogVariant.id == StockLevel.variant_id,
                    CatalogVariant.tenant_id == StockLevel.tenant_id,
                    CatalogVariant.environment_id == StockLevel.environment_id,
                ),
            )
            .join(
                CatalogProduct,
                and_(
                    CatalogProduct.id == CatalogVariant.product_id,
                    CatalogProduct.tenant_id == CatalogVariant.tenant_id,
                    CatalogProduct.environment_id == CatalogVariant.environment_id,
                ),
            )
            .join(
                InventoryLocation,
                and_(
                    InventoryLocation.id == StockLevel.location_id,
                    InventoryLocation.tenant_id == StockLevel.tenant_id,
                    InventoryLocation.environment_id == StockLevel.environment_id,
                ),
            )
            .where(self.levels.predicate())
        )
        if search:
            pattern = like_pattern(search.strip())
            statement = statement.where(
                CatalogProduct.name.ilike(pattern) | CatalogVariant.sku.ilike(pattern)
            )
        if location_id:
            statement = statement.where(StockLevel.location_id == location_id)
        if low_only:
            statement = statement.where(available <= threshold)
        total = await self.session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = await self.session.execute(
            statement.order_by(CatalogProduct.name, CatalogVariant.sku, InventoryLocation.name)
            .offset(page.offset)
            .limit(page.page_size)
        )
        items = []
        for level, variant, product, location in rows:
            limit = (
                variant.low_stock_threshold
                if variant.low_stock_threshold is not None
                else settings.low_stock_threshold
            )
            free = level.on_hand - level.reserved
            items.append(
                StockLevelView(
                    variant_id=variant.id,
                    product_id=product.id,
                    product_name=product.name,
                    variant_name=variant.name,
                    sku=variant.sku,
                    location_id=location.id,
                    location_name=location.name,
                    on_hand=level.on_hand,
                    reserved=level.reserved,
                    available=free,
                    low_stock_threshold=limit,
                    is_low=free <= limit,
                )
            )
        return Page(items=items, total=int(total or 0), page=page.page, page_size=page.page_size)

    async def availability(self, variant_ids: Sequence[UUID]) -> dict[UUID, Availability]:
        """Verified stock from the ledger-backed levels. PI must never guess this."""
        if not variant_ids:
            return {}
        variants = await self.session.scalars(
            self.variants.select().where(CatalogVariant.id.in_(list(variant_ids)))
        )
        tracked = {v.id: v.track_inventory for v in variants}
        sums = await self.session.execute(
            select(
                StockLevel.variant_id,
                func.coalesce(func.sum(StockLevel.on_hand), 0),
                func.coalesce(func.sum(StockLevel.reserved), 0),
            )
            .where(self.levels.predicate(), StockLevel.variant_id.in_(list(tracked)))
            .group_by(StockLevel.variant_id)
        )
        totals = {vid: (int(h), int(r)) for vid, h, r in sums}
        result = {}
        for vid, is_tracked in tracked.items():
            on_hand, reserved = totals.get(vid, (0, 0))
            result[vid] = Availability(
                variant_id=vid,
                on_hand=on_hand,
                reserved=reserved,
                available=on_hand - reserved,
                tracked=is_tracked,
            )
        return result

    # Movements ---------------------------------------------------------------------
    async def _locked_level(self, variant_id: UUID, location_id: UUID) -> StockLevel:
        await self.session.execute(
            insert(StockLevel)
            .values(
                tenant_id=self.scope.tenant_id,
                environment_id=self.scope.environment_id,
                variant_id=variant_id,
                location_id=location_id,
            )
            .on_conflict_do_nothing(constraint="uq_stock_levels_item")
        )
        level = await self.session.scalar(
            self.levels.select()
            .where(StockLevel.variant_id == variant_id, StockLevel.location_id == location_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if level is None:
            raise ResourceNotFound
        return level

    async def move(
        self,
        variant_id: UUID,
        quantity: int,
        kind: str,
        reason: str,
        *,
        location_id: UUID | None = None,
        ref_type: str | None = None,
        ref_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> StockMovement | None:
        """Apply one stock change under a row lock. Returns None for a replayed key."""
        if quantity == 0:
            raise BusinessRuleViolation("INVALID_QUANTITY", "Quantity must not be zero")
        if idempotency_key is not None:
            existing = await self.movements.find(StockMovement.idempotency_key == idempotency_key)
            if existing is not None:
                return None
        await self.variants.get(variant_id)
        location = (
            await self.locations.get(location_id) if location_id else await self.default_location()
        )
        level = await self._locked_level(variant_id, location.id)
        balance = level.on_hand + quantity
        if balance < 0 or balance < level.reserved:
            raise BusinessRuleViolation("INSUFFICIENT_STOCK", "Not enough stock available")
        level.on_hand = balance
        movement = await self.movements.add(
            self.movements.new(
                variant_id=variant_id,
                location_id=location.id,
                quantity=quantity,
                kind=kind,
                reason=reason[:240],
                balance_after=balance,
                ref_type=ref_type,
                ref_id=ref_id,
                idempotency_key=idempotency_key,
                actor_label=self.scope.actor_label[:80],
            )
        )
        if quantity < 0:
            await self._low_stock_alert(variant_id)
        return movement

    async def _low_stock_alert(self, variant_id: UUID) -> None:
        variant = await self.variants.get(variant_id)
        if not variant.track_inventory:
            return
        settings = await get_settings_row(self.session, self.scope)
        threshold = (
            variant.low_stock_threshold
            if variant.low_stock_threshold is not None
            else settings.low_stock_threshold
        )
        available = (await self.availability([variant_id]))[variant_id].available
        if available <= threshold:
            await notify(
                self.session,
                self.scope,
                "inventory",
                f"Low stock: {variant.sku}",
                f"{variant.name} has {available} available (threshold {threshold}).",
                link="/inventory?low_only=true",
                permission="inventory.read",
                severity="warning",
                dedupe_key=f"low-stock:{variant_id}:{date.today().isoformat()}",
            )

    async def adjust(self, data: StockAdjustment) -> StockMovement:
        self.scope.require("inventory.adjust")
        if data.kind in ("receipt", "return") and data.quantity <= 0:
            raise BusinessRuleViolation("INVALID_QUANTITY", "Receipts and returns add stock")
        movement = await self.move(
            data.variant_id,
            data.quantity,
            data.kind,
            data.reason,
            location_id=data.location_id,
            ref_type="manual",
        )
        assert movement is not None
        await record(
            self.session,
            "inventory.adjusted",
            scope=self.scope,
            entity_type="catalog_variant",
            entity_id=data.variant_id,
            details={
                "quantity": data.quantity,
                "kind": data.kind,
                "reason": data.reason,
                "balance_after": movement.balance_after,
            },
        )
        return movement

    async def movements_page(
        self, page: Pagination, variant_id: UUID | None = None
    ) -> Page[MovementView]:
        statement = self.movements.select()
        if variant_id:
            statement = statement.where(StockMovement.variant_id == variant_id)
        statement = statement.order_by(StockMovement.created_at.desc(), StockMovement.id)
        rows, total = await self.movements.page(statement, page)
        return to_page(MovementView, rows, total, page)

    async def low_stock_count(self) -> int:
        settings = await get_settings_row(self.session, self.scope)
        threshold = func.coalesce(CatalogVariant.low_stock_threshold, settings.low_stock_threshold)
        totals = (
            select(
                StockLevel.variant_id.label("variant_id"),
                func.sum(StockLevel.on_hand - StockLevel.reserved).label("available"),
            )
            .where(self.levels.predicate())
            .group_by(StockLevel.variant_id)
            .subquery()
        )
        count = await self.session.scalar(
            select(func.count())
            .select_from(CatalogVariant)
            .outerjoin(totals, totals.c.variant_id == CatalogVariant.id)
            .where(
                self.variants.predicate(),
                CatalogVariant.status == "active",
                CatalogVariant.track_inventory.is_(True),
                func.coalesce(totals.c.available, 0) <= threshold,
            )
        )
        return int(count or 0)
