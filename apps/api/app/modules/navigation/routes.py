from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.modules.access.dependencies import Scope, Session
from app.modules.navigation.registry import Section
from app.modules.navigation.service import NavigationService, NavigationView

router = APIRouter(prefix="/navigation", tags=["navigation"])


class OrderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order: list[str] = Field(min_length=1, max_length=100)


@router.get("", response_model=NavigationView)
async def navigation(scope: Scope, session: Session) -> NavigationView:
    return await NavigationService(session, scope).resolve()


@router.put("/preferences/{section}", response_model=NavigationView)
async def save_order(
    section: Section, data: OrderUpdate, scope: Scope, session: Session
) -> NavigationView:
    result = await NavigationService(session, scope).save_order(section, data.order)
    await session.commit()
    return result


@router.delete("/preferences/{section}", response_model=NavigationView)
async def reset_order(section: Section, scope: Scope, session: Session) -> NavigationView:
    result = await NavigationService(session, scope).reset(section)
    await session.commit()
    return result
