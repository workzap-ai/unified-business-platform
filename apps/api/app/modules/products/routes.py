from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, ConfigDict

from app.modules.access.dependencies import Scope, Session, require
from app.modules.products.service import ProductService, ProductState
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/products", tags=["products"])
Manage = Annotated[WorkspaceScope, Depends(require("admin.products.manage"))]
Key = Annotated[str, Path(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=40)]


class EnabledUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


@router.get("", response_model=list[ProductState])
async def products(scope: Scope, session: Session) -> list[ProductState]:
    return await ProductService(session, scope).states()


@router.post("/{key}/install", response_model=list[ProductState])
async def install(key: Key, scope: Manage, session: Session) -> list[ProductState]:
    service = ProductService(session, scope)
    await service.install(key)
    await session.commit()
    return await service.states()


@router.put("/{key}/environment", response_model=list[ProductState])
async def set_enabled(
    key: Key, data: EnabledUpdate, scope: Manage, session: Session
) -> list[ProductState]:
    service = ProductService(session, scope)
    await service.set_enabled(key, data.enabled)
    await session.commit()
    return await service.states()
