from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Specialist = Literal["operations", "hr", "finance", "crm"]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskCreate(StrictInput):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    description: str = Field(default="", max_length=4000)
    specialist: Specialist = "operations"
    assignee_id: UUID | None = None
    priority: Literal["low", "normal", "high"] = "normal"
    due_date: date | None = None


class TaskUpdate(StrictInput):
    id: UUID
    title: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
        | None
    ) = None
    status: Literal["todo", "in_progress", "done", "cancelled"] | None = None
    priority: Literal["low", "normal", "high"] | None = None
    assignee_id: UUID | None = None
    due_date: date | None = None


class ReadInput(StrictInput):
    area: Literal[
        "employees",
        "customers",
        "catalog",
        "inventory",
        "sales",
        "quotes",
        "orders",
        "billing",
        "finance",
        "tasks",
        "members",
    ]
    search: str = Field(default="", max_length=100)
    page: int = Field(default=1, ge=1, le=10000)


class Step(StrictInput):
    operation: Literal[
        "read",
        "summary",
        "navigate",
        "employees.create",
        "employees.update",
        "customers.create",
        "customers.update",
        "tasks.create",
        "tasks.update",
        "identity",
    ]
    arguments: dict[str, Any] = Field(default_factory=dict)


class Plan(StrictInput):
    message: str = Field(default="", max_length=1500)
    steps: list[Step] = Field(default_factory=list, max_length=6)


class ChatInput(StrictInput):
    message: Text
    # User-authored context only; previous assistant output is never trusted as business facts.
    history: list[Text] = Field(default_factory=list, max_length=8)
    current_page: str = Field(default="/", max_length=160)


class ProposalInput(StrictInput):
    operation: Literal[
        "employees.create",
        "employees.update",
        "customers.create",
        "customers.update",
        "tasks.create",
        "tasks.update",
    ]
    arguments: dict[str, Any]


class Decision(StrictInput):
    decision: Literal["confirm", "cancel"]


class Delegation(StrictInput):
    specialist: Specialist
    request: str = Field(min_length=1, max_length=2000)
