from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints, field_validator

Password = Annotated[str, StringConstraints(min_length=12, max_length=128)]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
OrgName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=160)]


def normalize_email(value: str) -> str:
    return value.strip().lower()


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: Annotated[str, StringConstraints(min_length=3, max_length=254)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return normalize_email(value)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: Password
    display_name: DisplayName
    organization_name: OrgName

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def _strength(cls, value: str) -> str:
        if len(set(value)) < 5:
            raise ValueError("Password is too simple")
        return value


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    new_password: Password

    @field_validator("new_password")
    @classmethod
    def _strength(cls, value: str) -> str:
        if len(set(value)) < 5:
            raise ValueError("Password is too simple")
        return value


class WorkspaceSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: UUID
    environment_id: UUID | None = None
    branch_id: UUID | None = None


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    display_name: str


class WorkspaceRef(BaseModel):
    id: UUID
    name: str
    key: str | None = None
    kind: str | None = None


class SessionView(BaseModel):
    user: UserView
    tenant: WorkspaceRef | None
    environment: WorkspaceRef | None
    branch: WorkspaceRef | None
    permissions: list[str]
    roles: list[str]
