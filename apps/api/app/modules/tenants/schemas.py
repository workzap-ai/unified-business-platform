from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Code = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=80, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$"
    ),
]


class BranchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    code: Code


class DepartmentCreate(BranchCreate):
    branch_id: UUID | None = None


class Rename(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name


class TenantView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    slug: str


class BranchView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    name: str
    code: str


class DepartmentView(BranchView):
    branch_id: UUID | None
