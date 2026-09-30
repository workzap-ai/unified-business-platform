"""Allowlisted workspace tools. Model output never supplies identity or permissions."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Pagination
from app.modules.access.models import MembershipRole, Role
from app.modules.access.service import membership_grants
from app.modules.audit.service import record
from app.modules.billing.models import Invoice
from app.modules.catalog.models import CatalogProduct
from app.modules.customers.models import Customer
from app.modules.customers.schemas import CustomerCreate, CustomerUpdate
from app.modules.customers.service import CustomerService
from app.modules.finance.models import Expense
from app.modules.hr.models import Employee
from app.modules.hr.service import EmployeeCreate, EmployeeUpdate, HRService
from app.modules.inventory.models import StockLevel
from app.modules.memberships.models import Membership
from app.modules.orders.models import Order
from app.modules.quotes.models import Quote
from app.modules.sales.models import SalesLead
from app.modules.tenants.context import require_active_scope
from app.modules.users.models import PlatformUser
from app.modules.workspace_agent.models import WorkspaceAgentAction, WorkspaceTask
from app.modules.workspace_agent.schemas import ReadInput, TaskCreate, TaskUpdate
from app.shared.errors import BusinessRuleViolation, PermissionDenied, ResourceNotFound
from app.shared.models import WorkspaceRow
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository, like_pattern

# Explicit projection: no credentials, encrypted HR details, provider configuration or PI tables.
AREAS: dict[str, tuple[type[WorkspaceRow], str, str, tuple[str, ...], str]] = {
    "customers": (Customer, "customers.read", "/customers", ("name", "company", "status"), "crm"),
    "catalog": (
        CatalogProduct,
        "catalog.read",
        "/catalog",
        ("name", "offering_type", "status"),
        "operations",
    ),
    "inventory": (
        StockLevel,
        "inventory.read",
        "/inventory",
        ("variant_id", "on_hand", "reserved"),
        "operations",
    ),
    "sales": (
        SalesLead,
        "sales.read",
        "/sales",
        ("title", "stage", "estimated_value", "currency"),
        "crm",
    ),
    "quotes": (Quote, "quotes.read", "/quotes", ("number", "status", "total", "currency"), "crm"),
    "orders": (
        Order,
        "orders.read",
        "/orders",
        ("number", "status", "total", "currency"),
        "operations",
    ),
    "billing": (
        Invoice,
        "billing.read",
        "/billing",
        ("number", "status", "total", "amount_paid", "currency", "due_date"),
        "finance",
    ),
    "finance": (
        Expense,
        "finance.read",
        "/finance",
        ("number", "category", "amount", "currency", "status"),
        "finance",
    ),
}
READ_PERMISSIONS = {area: spec[1] for area, spec in AREAS.items()} | {
    "employees": "hr.read",
    "members": "admin.members.read",
    "tasks": "tasks.read",
}
ROUTES = {area: spec[2] for area, spec in AREAS.items()} | {
    "employees": "/hr",
    "members": "/settings/members",
    "tasks": "/workspace-agent",
}
WRITE_PERMISSIONS = {
    "employees.create": ("hr.read", "hr.write"),
    "employees.update": ("hr.read", "hr.write"),
    "customers.create": ("customers.read", "customers.write"),
    "customers.update": ("customers.read", "customers.write"),
    "tasks.create": ("tasks.read", "tasks.write"),
    "tasks.update": ("tasks.read", "tasks.write"),
}


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def invalid(message: str) -> BusinessRuleViolation:
    return BusinessRuleViolation("AGENT_INPUT", message)


class AgentService:
    def __init__(self, session: AsyncSession, scope: WorkspaceScope) -> None:
        if scope.user_id is None or scope.membership_id is None or scope.is_system:
            raise PermissionDenied
        self.session, self.scope = session, scope
        self.actions = WorkspaceRepository(session, WorkspaceAgentAction, scope)
        self.tasks = WorkspaceRepository(session, WorkspaceTask, scope)

    async def identity(self) -> dict[str, Any]:
        assert self.scope.membership_id is not None
        _, roles = await membership_grants(
            self.session, self.scope.tenant_id, self.scope.membership_id
        )
        return {
            "name": self.scope.actor_label,
            "user_id": str(self.scope.user_id),
            "membership_id": str(self.scope.membership_id),
            "roles": roles,
            "tenant_id": str(self.scope.tenant_id),
            "environment_id": str(self.scope.environment_id),
            "permissions": sorted(self.scope.permissions),
            "read_areas": [k for k, p in READ_PERMISSIONS.items() if self.scope.can(p)],
            "actions": [
                k for k, ps in WRITE_PERMISSIONS.items() if all(self.scope.can(p) for p in ps)
            ],
            "specialists": ["operations", "hr", "finance", "crm"],
        }

    def task_query(self) -> Any:
        query = self.tasks.select()
        if not self.scope.can("tasks.manage"):
            query = query.where(
                or_(
                    WorkspaceTask.created_by == self.scope.user_id,
                    WorkspaceTask.assignee_id == self.scope.membership_id,
                )
            )
        return query

    async def task(self, task_id: UUID, *, lock: bool = False) -> WorkspaceTask:
        query = self.task_query().where(WorkspaceTask.id == task_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        row: WorkspaceTask | None = await self.session.scalar(query)
        if row is None:
            raise ResourceNotFound
        return row

    async def read(self, data: ReadInput) -> dict[str, Any]:
        self.scope.require(READ_PERMISSIONS[data.area])
        page = Pagination(page=data.page, page_size=25)
        specialist = "operations"
        query: Any
        fields: tuple[str, ...]
        if data.area == "employees":
            result = (
                await HRService(self.session, self.scope).search(page, data.search or None)
            ).model_dump(mode="json")
            specialist = "hr"
        elif data.area == "members":
            query = (
                select(Membership.id, PlatformUser.display_name, Role.key.label("role"))
                .join(PlatformUser, PlatformUser.id == Membership.user_id)
                .join(
                    MembershipRole,
                    (MembershipRole.membership_id == Membership.id)
                    & (MembershipRole.tenant_id == Membership.tenant_id),
                )
                .join(
                    Role,
                    (Role.id == MembershipRole.role_id) & (Role.tenant_id == Membership.tenant_id),
                )
                .where(
                    Membership.tenant_id == self.scope.tenant_id,
                    Membership.status == "active",
                    PlatformUser.status == "active",
                )
            )
            if data.search:
                query = query.where(PlatformUser.display_name.ilike(like_pattern(data.search)))
            total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
            rows = (
                await self.session.execute(
                    query.order_by(PlatformUser.display_name, Membership.id, Role.key)
                    .offset(page.offset)
                    .limit(25)
                )
            ).mappings()
            result = {
                "items": [dict(r) for r in rows],
                "total": total,
                "page": page.page,
                "page_size": 25,
                "count_unit": "membership-role pairs",
            }
        else:
            if data.area == "tasks":
                model: type[WorkspaceRow] = WorkspaceTask
                fields = (
                    "title",
                    "description",
                    "status",
                    "priority",
                    "assignee_id",
                    "specialist",
                    "due_date",
                    "updated_at",
                )
                query = self.task_query()
            else:
                model, _, _, fields, specialist = AREAS[data.area]
                query = WorkspaceRepository(self.session, model, self.scope).select()
            if data.search:
                searchable = [
                    getattr(model, f).ilike(like_pattern(data.search))
                    for f in fields
                    if f in {"name", "number", "title", "company"}
                ]
                if searchable:
                    query = query.where(or_(*searchable))
            total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
            projection = query.with_only_columns(model.id, *(getattr(model, f) for f in fields))
            rows = (
                await self.session.execute(
                    projection.order_by(model.created_at.desc(), model.id)
                    .offset(page.offset)
                    .limit(25)
                )
            ).mappings()
            result = {
                "items": [dict(r) for r in rows],
                "total": total,
                "page": page.page,
                "page_size": 25,
            }
        result["search"] = data.search
        return cast(
            dict[str, Any],
            json_safe(
                {"area": data.area, "specialist": specialist, "route": ROUTES[data.area], **result}
            ),
        )

    async def summary(self) -> list[dict[str, Any]]:
        results = []
        for area, permission in READ_PERMISSIONS.items():
            if self.scope.can(permission):
                result = await self.read(ReadInput(area=area))
                result["items"] = result["items"][:3]
                result["sample_only"] = True
                results.append(result)
        return results

    async def _assignee(self, assignee: UUID | None) -> None:
        if assignee is None:
            return
        if assignee != self.scope.membership_id:
            self.scope.require("tasks.manage")
        found = await self.session.scalar(
            select(Membership.id)
            .join(PlatformUser, PlatformUser.id == Membership.user_id)
            .where(
                Membership.tenant_id == self.scope.tenant_id,
                Membership.id == assignee,
                Membership.status == "active",
                PlatformUser.status == "active",
            )
        )
        if found is None:
            raise ResourceNotFound

    async def _employees(self, raw: Any) -> list[EmployeeCreate]:
        if not isinstance(raw, list) or not 1 <= len(raw) <= 100:
            raise invalid("Provide between 1 and 100 employee rows.")
        rows = [EmployeeCreate.model_validate(r) for r in raw]
        emails: set[str] = set()
        for row in rows:
            if row.salary is not None or row.salary_currency is not None:
                self.scope.require("hr.sensitive")
            await HRService(self.session, self.scope)._check_refs(row.department_id, row.manager_id)
            if row.email:
                email = str(row.email).lower()
                existing = await WorkspaceRepository(self.session, Employee, self.scope).find(
                    func.lower(Employee.email) == email
                )
                if email in emails or existing is not None:
                    raise invalid("Duplicate employee email. Resolve duplicates before importing.")
                emails.add(email)
        return rows

    async def _validate(
        self, operation: str, arguments: dict[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        if operation not in WRITE_PERMISSIONS:
            raise invalid("This action is not supported by Agent Beta.")
        permissions = list(WRITE_PERMISSIONS[operation])
        self.scope.require(*permissions)
        payload: dict[str, Any]
        if operation == "employees.create":
            if set(arguments) != {"rows"}:
                raise invalid("Employee creation requires a rows array only.")
            rows = await self._employees(arguments["rows"])
            payload = {"rows": [row.model_dump(mode="json") for row in rows]}
            if any(r.salary is not None or r.salary_currency is not None for r in rows):
                permissions.append("hr.sensitive")
        elif operation in {"employees.update", "customers.update"}:
            if set(arguments) != {"id", "changes"}:
                raise invalid("Updates require a record id and changes.")
            row_id = UUID(str(arguments["id"]))
            model = Employee if operation.startswith("employees") else Customer
            row = await WorkspaceRepository(self.session, model, self.scope).get(row_id)
            changes_model = EmployeeUpdate if model is Employee else CustomerUpdate
            changes = changes_model.model_validate(arguments["changes"]).model_dump(
                mode="json", exclude_unset=True
            )
            if not changes:
                raise invalid("Provide at least one field to update.")
            if model is Employee:
                if {"salary", "salary_currency"} & changes.keys():
                    self.scope.require("hr.sensitive")
                    permissions.append("hr.sensitive")
                update = EmployeeUpdate.model_validate(changes)
                await HRService(self.session, self.scope)._check_refs(
                    update.department_id, update.manager_id
                )
            payload = {"id": str(row_id), "changes": changes, "version": str(row.updated_at)}
        elif operation == "customers.create":
            payload = CustomerCreate.model_validate(arguments).model_dump(mode="json")
        elif operation == "tasks.create":
            task = TaskCreate.model_validate(arguments)
            if task.assignee_id is None:
                task.assignee_id = self.scope.membership_id
            await self._assignee(task.assignee_id)
            payload = task.model_dump(mode="json")
            if task.assignee_id != self.scope.membership_id:
                permissions.append("tasks.manage")
        else:
            update_task = TaskUpdate.model_validate(arguments)
            row = await self.task(update_task.id)
            if row.created_by != self.scope.user_id and row.assignee_id != self.scope.membership_id:
                permissions.append("tasks.manage")
            payload = update_task.model_dump(mode="json", exclude_unset=True)
            if len(payload) == 1:
                raise invalid("Provide a task change.")
            if "assignee_id" in payload:
                await self._assignee(update_task.assignee_id)
                if update_task.assignee_id != self.scope.membership_id:
                    self.scope.require("tasks.manage")
                    permissions.append("tasks.manage")
            payload["version"] = str(row.updated_at)
        return payload, permissions

    async def propose(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            payload, permissions = await self._validate(operation, arguments)
        except (ValueError, ValidationError):
            raise invalid(
                "Some fields are missing or invalid. Check names, dates, IDs and required fields."
            ) from None
        await require_active_scope(self.session, self.scope.tenant_scope(), for_write=True)
        action = await self.actions.add(
            self.actions.new(
                user_id=self.scope.user_id,
                operation=operation,
                payload=payload,
                required_permissions=permissions,
                expires_at=datetime.now(UTC) + timedelta(minutes=30),
            )
        )
        await record(
            self.session,
            "workspace_agent.proposed",
            scope=self.scope,
            entity_type="workspace_agent_action",
            entity_id=action.id,
            details={"operation": operation, "row_count": len(payload.get("rows", []))},
        )
        return self.action_view(action)

    def action_view(self, action: WorkspaceAgentAction) -> dict[str, Any]:
        self.scope.require(*action.required_permissions)
        return cast(
            dict[str, Any],
            json_safe(
                {
                    "id": action.id,
                    "operation": action.operation,
                    "preview": {k: v for k, v in action.payload.items() if k != "version"},
                    "status": action.status,
                    "expires_at": action.expires_at,
                    "result": action.result,
                }
            ),
        )

    async def pending(self) -> list[dict[str, Any]]:
        rows = await self.session.scalars(
            self.actions.select()
            .where(
                WorkspaceAgentAction.user_id == self.scope.user_id,
                WorkspaceAgentAction.status == "pending",
                WorkspaceAgentAction.expires_at > datetime.now(UTC),
            )
            .order_by(WorkspaceAgentAction.created_at.desc())
            .limit(30)
        )
        return [
            self.action_view(r)
            for r in rows
            if set(r.required_permissions) <= self.scope.permissions
        ]

    async def decide(self, action_id: UUID, decision: str) -> dict[str, Any]:
        # Even owners cannot approve another user's draft.
        action = await self.session.scalar(
            self.actions.select()
            .where(
                WorkspaceAgentAction.id == action_id,
                WorkspaceAgentAction.user_id == self.scope.user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if action is None:
            raise ResourceNotFound
        self.scope.require(*action.required_permissions)
        if action.status == "applied":
            return self.action_view(action)  # retry after a lost response never duplicates a write
        if action.status != "pending" or action.expires_at <= datetime.now(UTC):
            raise BusinessRuleViolation(
                "AGENT_ACTION_EXPIRED",
                "This draft expired or was cancelled. Create a fresh preview.",
                409,
            )
        if decision == "cancel":
            action.status = "cancelled"
        else:
            await require_active_scope(self.session, self.scope.tenant_scope(), for_write=True)
            operation, payload = action.operation, action.payload
            # Serializes employee bulk inserts in this workspace, including duplicate checks.
            if operation.startswith("employees"):
                lock_key = int.from_bytes(
                    hashlib.sha256(
                        f"agent-employees:{self.scope.tenant_id}:{self.scope.environment_id}".encode()
                    ).digest()[:8],
                    "big",
                    signed=True,
                )
                await self.session.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key}
                )
            ids: list[str] = []
            if operation == "employees.create":
                for employee in await self._employees(payload["rows"]):
                    result = await HRService(self.session, self.scope).create(employee)
                    ids.append(str(result.id))
            elif operation in {"employees.update", "customers.update", "tasks.update"}:
                row_id = UUID(payload["id"])
                current: WorkspaceRow
                if operation == "tasks.update":
                    current = await self.task(row_id, lock=True)
                else:
                    model = Employee if operation.startswith("employees") else Customer
                    current = await WorkspaceRepository(self.session, model, self.scope).get(
                        row_id, for_update=True
                    )
                if str(current.updated_at) != payload["version"]:
                    raise BusinessRuleViolation(
                        "AGENT_RECORD_CHANGED",
                        "This record changed after the preview. Create a fresh preview.",
                        409,
                    )
                if operation == "employees.update":
                    await HRService(self.session, self.scope).update(
                        row_id, EmployeeUpdate.model_validate(payload["changes"])
                    )
                elif operation == "customers.update":
                    await CustomerService(self.session, self.scope).update(
                        row_id, CustomerUpdate.model_validate(payload["changes"])
                    )
                else:
                    changes = TaskUpdate.model_validate(
                        {k: v for k, v in payload.items() if k != "version"}
                    )
                    if "assignee_id" in changes.model_fields_set:
                        await self._assignee(changes.assignee_id)
                    for key, value in changes.model_dump(
                        exclude_unset=True, exclude={"id"}
                    ).items():
                        if value is not None or key in {"assignee_id", "due_date"}:
                            setattr(current, key, value)
                ids.append(str(row_id))
            elif operation == "customers.create":
                customer = await CustomerService(self.session, self.scope).create(
                    CustomerCreate.model_validate(payload)
                )
                ids.append(str(customer.id))
            elif operation == "tasks.create":
                task_data = TaskCreate.model_validate(payload)
                await self._assignee(task_data.assignee_id)
                created = await self.tasks.add(
                    self.tasks.new(created_by=self.scope.user_id, **task_data.model_dump())
                )
                ids.append(str(created.id))
            else:
                raise invalid("Unsupported action.")
            action.status = "applied"
            action.result = {"ids": ids, "count": len(ids)}
        await self.session.flush()
        await record(
            self.session,
            f"workspace_agent.{action.status}",
            scope=self.scope,
            entity_type="workspace_agent_action",
            entity_id=action.id,
            details={"operation": action.operation, "count": (action.result or {}).get("count", 0)},
        )
        return self.action_view(action)
