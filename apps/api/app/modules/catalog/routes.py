from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.pagination import Page, Pagination
from app.modules.access.dependencies import Session, require
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
from app.modules.catalog.service import CatalogService
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/catalog", tags=["catalog"])
Read = Annotated[WorkspaceScope, Depends(require("catalog.read"))]
Write = Annotated[WorkspaceScope, Depends(require("catalog.write"))]
Paging = Annotated[Pagination, Query()]


@router.get("/categories", response_model=list[CategoryView])
async def categories(scope: Read, session: Session) -> list[CategoryView]:
    return await CatalogService(session, scope).list_categories()


@router.post("/categories", response_model=CategoryView, status_code=status.HTTP_201_CREATED)
async def create_category(data: CategoryCreate, scope: Write, session: Session) -> CategoryView:
    row = await CatalogService(session, scope).create_category(data)
    await session.commit()
    return CategoryView.model_validate(row)


@router.get("/products", response_model=Page[ProductListItem])
async def products(
    scope: Read,
    session: Session,
    pagination: Paging,
    search: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[Literal["active", "inactive"] | None, Query(alias="status")] = None,
    category_id: UUID | None = None,
) -> Page[ProductListItem]:
    return await CatalogService(session, scope).list_products(
        pagination, search, status_filter, category_id
    )


@router.post("/products", response_model=ProductDetail, status_code=status.HTTP_201_CREATED)
async def create_product(data: ProductCreate, scope: Write, session: Session) -> ProductDetail:
    service = CatalogService(session, scope)
    product = await service.create_product(data)
    await session.commit()
    return await service.detail(product.id)


@router.get("/products/{product_id}", response_model=ProductDetail)
async def product(product_id: UUID, scope: Read, session: Session) -> ProductDetail:
    return await CatalogService(session, scope).detail(product_id)


@router.patch("/products/{product_id}", response_model=ProductDetail)
async def update_product(
    product_id: UUID, data: ProductUpdate, scope: Write, session: Session
) -> ProductDetail:
    service = CatalogService(session, scope)
    await service.update_product(product_id, data)
    await session.commit()
    return await service.detail(product_id)


@router.post(
    "/products/{product_id}/variants",
    response_model=VariantView,
    status_code=status.HTTP_201_CREATED,
)
async def add_variant(
    product_id: UUID, data: VariantCreate, scope: Write, session: Session
) -> VariantView:
    row = await CatalogService(session, scope).add_variant(product_id, data)
    await session.commit()
    return VariantView.model_validate(row)


@router.patch("/variants/{variant_id}", response_model=VariantView)
async def update_variant(
    variant_id: UUID, data: VariantUpdate, scope: Write, session: Session
) -> VariantView:
    row = await CatalogService(session, scope).update_variant(variant_id, data)
    await session.commit()
    return VariantView.model_validate(row)
