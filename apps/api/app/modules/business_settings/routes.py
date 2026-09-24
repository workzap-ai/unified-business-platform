from typing import Annotated

from fastapi import APIRouter, Depends

from app.modules.access.dependencies import Scope, Session, require
from app.modules.business_settings.service import (
    BusinessSettingsUpdate,
    BusinessSettingsView,
    get_settings_row,
    update_settings,
)
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/settings/business", tags=["settings"])
Manage = Annotated[WorkspaceScope, Depends(require("settings.manage"))]


@router.get("", response_model=BusinessSettingsView)
async def business_settings(scope: Scope, session: Session) -> BusinessSettingsView:
    row = await get_settings_row(session, scope)
    await session.commit()
    return BusinessSettingsView.model_validate(row)


@router.patch("", response_model=BusinessSettingsView)
async def update_business_settings(
    data: BusinessSettingsUpdate, scope: Manage, session: Session
) -> BusinessSettingsView:
    row = await update_settings(session, scope, data)
    await session.commit()
    return BusinessSettingsView.model_validate(row)
