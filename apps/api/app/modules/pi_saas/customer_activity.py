"""A customer's activity for the pi app: GET /customers/{id}/activities.

The same read-only feed as Owner OS's customer Activity tab (changes, notes, documents,
conversations; newest first, paged). Only this one read is mounted for the pi app, not
the rest of the core customers routes.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.pagination import Page, Pagination
from app.modules.access.dependencies import Scope, Session
from app.modules.customers.schemas import ActivityView
from app.modules.customers.service import CustomerService

router = APIRouter(prefix="/customers", tags=["customer-activity"])


@router.get("/{customer_id}/activities", response_model=Page[ActivityView])
async def activities(
    customer_id: UUID,
    scope: Scope,
    session: Session,
    pagination: Annotated[Pagination, Depends()],
) -> Page[ActivityView]:
    scope.require("customers.read")
    return await CustomerService(session, scope).activities_page(customer_id, pagination)
