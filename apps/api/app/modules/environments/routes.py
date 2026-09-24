from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.modules.access.dependencies import Scope, Session, require
from app.modules.audit.service import record
from app.modules.environments.models import Environment
from app.shared.errors import BusinessRuleViolation, Conflict, ResourceNotFound
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/environments", tags=["environments"])
Manage = Annotated[WorkspaceScope, Depends(require("admin.environments.manage"))]
Key = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=2, max_length=40, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$"
    ),
]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class EnvironmentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    key: str
    name: str
    kind: str
    status: str
    is_default: bool


class EnvironmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: Key
    name: Name
    kind: Literal["production", "staging", "development"]


class EnvironmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    status: Literal["active", "archived"]


@router.get("", response_model=list[EnvironmentView])
async def environments(scope: Scope, session: Session) -> list[EnvironmentView]:
    rows = await session.scalars(
        select(Environment)
        .where(Environment.tenant_id == scope.tenant_id)
        .order_by(Environment.is_default.desc(), Environment.name)
        .limit(50)
    )
    return [EnvironmentView.model_validate(r) for r in rows]


@router.post("", response_model=EnvironmentView, status_code=status.HTTP_201_CREATED)
async def create_environment(
    data: EnvironmentCreate, scope: Manage, session: Session
) -> EnvironmentView:
    try:
        async with session.begin_nested():
            env = Environment(tenant_id=scope.tenant_id, **data.model_dump())
            session.add(env)
            await session.flush()
    except IntegrityError:
        raise Conflict("An environment with this key already exists") from None
    await record(
        session,
        "environment.created",
        scope=scope,
        entity_type="environment",
        entity_id=env.id,
        details={"key": data.key, "kind": data.kind},
        include_environment=False,
    )
    await session.commit()
    return EnvironmentView.model_validate(env)


@router.patch("/{environment_id}", response_model=EnvironmentView)
async def update_environment(
    environment_id: UUID, data: EnvironmentUpdate, scope: Manage, session: Session
) -> EnvironmentView:
    env = await session.scalar(
        select(Environment).where(
            Environment.tenant_id == scope.tenant_id, Environment.id == environment_id
        )
    )
    if env is None:
        raise ResourceNotFound
    if data.status == "archived" and (env.is_default or env.id == scope.environment_id):
        raise BusinessRuleViolation(
            "ENVIRONMENT_IN_USE", "The default or current environment cannot be archived"
        )
    env.name, env.status = data.name, data.status
    await record(
        session,
        "environment.updated",
        scope=scope,
        entity_type="environment",
        entity_id=env.id,
        details={"status": data.status},
        include_environment=False,
    )
    await session.commit()
    return EnvironmentView.model_validate(env)
