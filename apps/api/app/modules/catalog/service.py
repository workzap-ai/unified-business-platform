from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, Pagination
from app.modules.audit.service import record
from app.modules.business_settings.service import get_settings_row
from app.modules.catalog.models import CatalogCategory, CatalogProduct, CatalogVariant
from app.modules.catalog.schemas import (
    CategoryCreate,
    CategoryView,
    ProductCreate,
    ProductDetail,
    ProductListItem,
    ProductUpdate,
    VariantCreate,
    VariantUpdate,
    VariantView,
)
from app.shared.errors import BusinessRuleViolation, Conflict
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository, like_pattern


class CatalogService:
    def __init__(self, session: AsyncSession, scope: WorkspaceScope) -> None:
        self.session, self.scope = session, scope
        self.categories = WorkspaceRepository(session, CatalogCategory, scope)
        self.products = WorkspaceRepository(session, CatalogProduct, scope)
        self.variants = WorkspaceRepository(session, CatalogVariant, scope)

    # Categories -----------------------------------------------------------------
    async def list_categories(self) -> list[CategoryView]:
        rows = await self.session.scalars(
            self.categories.select().order_by(CatalogCategory.name).limit(500)
        )
        return [CategoryView.model_validate(r) for r in rows]

    async def create_category(self, data: CategoryCreate) -> CatalogCategory:
        self.scope.require("catalog.write")
        try:
            async with self.session.begin_nested():
                row = await self.categories.add(self.categories.new(**data.model_dump()))
        except IntegrityError:
            raise Conflict("A category with this slug already exists") from None
        await record(
            self.session,
            "catalog.category_created",
            scope=self.scope,
            entity_type="catalog_category",
            entity_id=row.id,
        )
        return row

    # Products -------------------------------------------------------------------
    async def list_products(
        self,
        page: Pagination,
        search: str | None = None,
        status: str | None = None,
        category_id: UUID | None = None,
    ) -> Page[ProductListItem]:
        statement = self.products.select()
        if search:
            pattern = like_pattern(search.strip())
            sku_match = (
                select(CatalogVariant.product_id)
                .where(self.variants.predicate(), CatalogVariant.sku.ilike(pattern))
                .scalar_subquery()
            )
            statement = statement.where(
                or_(CatalogProduct.name.ilike(pattern), CatalogProduct.id.in_(sku_match))
            )
        if status:
            statement = statement.where(CatalogProduct.status == status)
        if category_id:
            statement = statement.where(CatalogProduct.category_id == category_id)
        statement = statement.order_by(CatalogProduct.name, CatalogProduct.id)
        rows, total = await self.products.page(statement, page)
        items = await self._list_items(rows)
        return Page(items=items, total=total, page=page.page, page_size=page.page_size)

    async def _list_items(self, rows: Sequence[CatalogProduct]) -> list[ProductListItem]:
        ids = [r.id for r in rows]
        stats: dict[UUID, tuple[int, object, object, str | None]] = {}
        if ids:
            result = await self.session.execute(
                select(
                    CatalogVariant.product_id,
                    func.count(),
                    func.min(CatalogVariant.price),
                    func.max(CatalogVariant.price),
                    func.min(CatalogVariant.currency),
                )
                .where(self.variants.predicate(), CatalogVariant.product_id.in_(ids))
                .group_by(CatalogVariant.product_id)
            )
            stats = {pid: (int(n), lo, hi, cur) for pid, n, lo, hi, cur in result}
        names = await self._category_names({r.category_id for r in rows if r.category_id})
        items = []
        for row in rows:
            count, lo, hi, cur = stats.get(row.id, (0, None, None, None))
            items.append(
                ProductListItem.model_validate(
                    {
                        **{
                            c: getattr(row, c)
                            for c in ProductListItem.model_fields
                            if hasattr(row, c)
                        },
                        "category_name": names.get(row.category_id) if row.category_id else None,
                        "variant_count": count,
                        "min_price": lo,
                        "max_price": hi,
                        "currency": cur,
                    }
                )
            )
        return items

    async def _category_names(self, ids: set[UUID]) -> dict[UUID, str]:
        if not ids:
            return {}
        rows = await self.session.execute(
            select(CatalogCategory.id, CatalogCategory.name).where(
                self.categories.predicate(), CatalogCategory.id.in_(ids)
            )
        )
        return {i: n for i, n in rows}

    async def detail(self, product_id: UUID) -> ProductDetail:
        product = await self.products.get(product_id)
        variants = await self.session.scalars(
            self.variants.select()
            .where(CatalogVariant.product_id == product.id)
            .order_by(CatalogVariant.sku)
            .limit(200)
        )
        names = await self._category_names({product.category_id} if product.category_id else set())
        return ProductDetail(
            offering_type=product.offering_type,
            id=product.id,
            name=product.name,
            description=product.description,
            category_id=product.category_id,
            status=product.status,
            pi_visible=product.pi_visible,
            attributes=product.attributes,
            created_at=product.created_at,
            category_name=names.get(product.category_id) if product.category_id else None,
            variants=[VariantView.model_validate(v) for v in variants],
        )

    async def create_product(self, data: ProductCreate) -> CatalogProduct:
        self.scope.require("catalog.write")
        for variant in data.variants:
            await self._validate_tracking(data.offering_type, variant.track_inventory)
        if data.category_id:
            await self.categories.get(data.category_id)
        if len({v.sku.lower() for v in data.variants}) != len(data.variants):
            raise BusinessRuleViolation("DUPLICATE_SKU", "Each variant needs a unique SKU")
        product = await self.products.add(
            self.products.new(**data.model_dump(exclude={"variants"}))
        )
        try:
            async with self.session.begin_nested():
                for variant in data.variants:
                    await self.variants.add(
                        self.variants.new(product_id=product.id, **variant.model_dump())
                    )
        except IntegrityError:
            raise Conflict("A variant with this SKU already exists") from None
        await record(
            self.session,
            "catalog.product_created",
            scope=self.scope,
            entity_type="catalog_product",
            entity_id=product.id,
            details={"variants": len(data.variants)},
        )
        return product

    async def update_product(self, product_id: UUID, data: ProductUpdate) -> CatalogProduct:
        self.scope.require("catalog.write")
        product = await self.products.get(product_id, for_update=True)
        changes = data.model_dump(exclude_unset=True)
        if changes.get("category_id"):
            await self.categories.get(changes["category_id"])
        for field in ("name", "description", "category_id", "status", "pi_visible", "attributes"):
            if field in changes and (changes[field] is not None or field == "category_id"):
                setattr(product, field, changes[field])
        await self.session.flush()
        await record(
            self.session,
            "catalog.product_updated",
            scope=self.scope,
            entity_type="catalog_product",
            entity_id=product.id,
            details={"fields": sorted(changes)},
        )
        return product

    async def add_variant(self, product_id: UUID, data: VariantCreate) -> CatalogVariant:
        self.scope.require("catalog.write")
        product = await self.products.get(product_id)
        await self._validate_tracking(product.offering_type, data.track_inventory)
        try:
            async with self.session.begin_nested():
                variant = await self.variants.add(
                    self.variants.new(product_id=product_id, **data.model_dump())
                )
        except IntegrityError:
            raise Conflict("A variant with this SKU already exists") from None
        await record(
            self.session,
            "catalog.variant_created",
            scope=self.scope,
            entity_type="catalog_variant",
            entity_id=variant.id,
        )
        return variant

    async def update_variant(self, variant_id: UUID, data: VariantUpdate) -> CatalogVariant:
        self.scope.require("catalog.write")
        variant = await self.variants.get(variant_id, for_update=True)
        product = await self.products.get(variant.product_id)
        await self._validate_tracking(
            product.offering_type,
            data.track_inventory if data.track_inventory is not None else variant.track_inventory,
        )
        changes = data.model_dump(exclude_unset=True)
        old_price = variant.price
        for field in (
            "name",
            "price",
            "status",
            "track_inventory",
            "low_stock_threshold",
            "attributes",
        ):
            if field in changes and (changes[field] is not None or field == "low_stock_threshold"):
                setattr(variant, field, changes[field])
        await self.session.flush()
        details: dict[str, object] = {"fields": sorted(changes)}
        if "price" in changes and changes["price"] != old_price:
            details.update(old_price=str(old_price), new_price=str(variant.price))
        await record(
            self.session,
            "catalog.variant_updated",
            scope=self.scope,
            entity_type="catalog_variant",
            entity_id=variant.id,
            details=details,
        )
        return variant

    async def _validate_tracking(self, offering_type: str, tracked: bool) -> None:
        if not tracked:
            return
        settings = await get_settings_row(self.session, self.scope)
        if offering_type == "service" or settings.business_type == "service_business":
            raise BusinessRuleViolation(
                "INVENTORY_NOT_APPLICABLE",
                "Services do not track stock; enable a product or hybrid business "
                "for physical items",
            )

    # Read helpers used by other modules and PI tools ---------------------------------
    async def variants_by_ids(self, ids: Sequence[UUID]) -> dict[UUID, CatalogVariant]:
        if not ids:
            return {}
        rows = await self.session.scalars(
            self.variants.select().where(CatalogVariant.id.in_(list(ids)))
        )
        return {v.id: v for v in rows}

    async def sellable_variant(self, variant_id: UUID) -> tuple[CatalogVariant, CatalogProduct]:
        variant = await self.variants.get(variant_id)
        product = await self.products.get(variant.product_id)
        if variant.status != "active" or product.status != "active":
            raise BusinessRuleViolation("VARIANT_UNAVAILABLE", "This item is not available")
        return variant, product

    async def search_for_assistant(
        self, query: str, limit: int = 5
    ) -> list[tuple[CatalogProduct, list[CatalogVariant]]]:
        """Approved, active products only (pi_visible) for PI's controlled tools."""
        terms = [t for t in query.strip().split() if len(t) >= 2][:6]
        if not terms:
            return []
        conditions = []
        for term in terms:
            pattern = like_pattern(term)
            sku_match = (
                select(CatalogVariant.product_id)
                .where(self.variants.predicate(), CatalogVariant.sku.ilike(pattern))
                .scalar_subquery()
            )
            conditions.append(
                or_(
                    CatalogProduct.name.ilike(pattern),
                    CatalogProduct.description.ilike(pattern),
                    CatalogProduct.id.in_(sku_match),
                )
            )
        products = (
            await self.session.scalars(
                self.products.select()
                .where(
                    CatalogProduct.status == "active",
                    CatalogProduct.pi_visible.is_(True),
                    or_(*conditions),
                )
                .order_by(func.similarity(CatalogProduct.name, query).desc(), CatalogProduct.name)
                .limit(limit)
            )
        ).all()
        if not products:
            return []
        variants = await self.session.scalars(
            self.variants.select()
            .where(
                CatalogVariant.product_id.in_([p.id for p in products]),
                CatalogVariant.status == "active",
            )
            .order_by(CatalogVariant.sku)
        )
        grouped: dict[UUID, list[CatalogVariant]] = {}
        for v in variants:
            grouped.setdefault(v.product_id, []).append(v)
        return [(p, grouped.get(p.id, [])) for p in products]
