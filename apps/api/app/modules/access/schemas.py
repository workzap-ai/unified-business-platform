from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

RoleKey = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=2, max_length=60, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$"
    ),
]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=240)]


class PermissionView(BaseModel):
    key: str
    label: str
    group: str


class RoleView(BaseModel):
    id: UUID
    key: str
    name: str
    description: str
    is_system: bool
    permissions: list[str]
    member_count: int


class RoleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: RoleKey
    name: Name
    description: Description = ""
    permissions: list[str] = Field(max_length=100)


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    description: Description = ""
    permissions: list[str] = Field(max_length=100)


class MemberView(BaseModel):
    membership_id: UUID
    user_id: UUID
    email: str
    display_name: str
    status: str
    roles: list[str]
    role_ids: list[UUID]
    joined_at: datetime


class MemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    display_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)
    ]
    # Only used when the email has no platform account yet; never overwrites credentials.
    initial_password: Annotated[str, StringConstraints(min_length=12, max_length=128)] | None = None
    role_ids: list[UUID] = Field(min_length=1, max_length=10)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return value.strip().lower()


class MemberRolesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_ids: list[UUID] = Field(min_length=1, max_length=10)
