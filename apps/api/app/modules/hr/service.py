from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, Pagination
from app.modules.audit.service import record
from app.modules.customers.schemas import normalize_phone
from app.modules.departments.models import Department
from app.modules.hr.models import Employee
from app.shared.errors import BusinessRuleViolation, ResourceNotFound
from app.shared.money import Currency, Money
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository, like_pattern

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
EmploymentType = Literal["full_time", "part_time", "contract", "intern"]
Status = Literal["active", "on_leave", "terminated"]


class EmployeeFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    department_id: UUID | None = None
    manager_id: UUID | None = None
    salary: Money | None = None
    salary_currency: Currency | None = None

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return normalize_phone(value)


class EmployeeCreate(EmployeeFields):
    full_name: Name
    job_title: Title
    employment_type: EmploymentType
    hire_date: date


class EmployeeUpdate(EmployeeFields):
    full_name: Name | None = None
    job_title: Title | None = None
    employment_type: EmploymentType | None = None
    status: Status | None = None
    termination_date: date | None = None


class EmployeeView(BaseModel):
    id: UUID
    full_name: str
    email: str | None
    phone: str | None
    job_title: str
    department_id: UUID | None
    department_name: str | None
    manager_id: UUID | None
    employment_type: str
    status: str
    hire_date: date
    termination_date: date | None
    salary: Decimal | None = None
    salary_currency: str | None = None
    gender: str | None = None
    work_arrangement: str | None = None
    date_of_birth: date | None = None  # hr.sensitive only
    has_personal_details: bool = False
    sensitive_visible: bool
    created_at: datetime


class Headcount(BaseModel):
    total: int
    active: int
    on_leave: int
    terminated: int
    by_department: list[tuple[str, int]]


class HRService:
    def __init__(self, session: AsyncSession, scope: WorkspaceScope) -> None:
        self.session, self.scope = session, scope
        self.employees = WorkspaceRepository(session, Employee, scope)

    def _view(self, row: Employee, departments: dict[UUID, str]) -> EmployeeView:
        sensitive = self.scope.can("hr.sensitive")
        return EmployeeView(
            id=row.id,
            full_name=row.full_name,
            email=row.email,
            phone=row.phone,
            job_title=row.job_title,
            department_id=row.department_id,
            department_name=departments.get(row.department_id) if row.department_id else None,
            manager_id=row.manager_id,
            employment_type=row.employment_type,
            status=row.status,
            hire_date=row.hire_date,
            termination_date=row.termination_date,
            salary=row.salary if sensitive else None,
            salary_currency=row.salary_currency if sensitive else None,
            gender=row.gender,
            work_arrangement=row.work_arrangement,
            date_of_birth=row.date_of_birth if sensitive else None,
            has_personal_details=row.personal_details_encrypted is not None,
            sensitive_visible=sensitive,
            created_at=row.created_at,
        )

    async def _departments(self, ids: set[UUID]) -> dict[UUID, str]:
        if not ids:
            return {}
        rows = await self.session.execute(
            select(Department.id, Department.name).where(
                Department.tenant_id == self.scope.tenant_id, Department.id.in_(ids)
            )
        )
        return {i: n for i, n in rows}

    async def search(
        self,
        page: Pagination,
        search: str | None = None,
        status: str | None = None,
        department_id: UUID | None = None,
    ) -> Page[EmployeeView]:
        statement = self.employees.select()
        if search:
            pattern = like_pattern(search.strip())
            statement = statement.where(
                Employee.full_name.ilike(pattern) | Employee.job_title.ilike(pattern)
            )
        if status:
            statement = statement.where(Employee.status == status)
        if department_id:
            statement = statement.where(Employee.department_id == department_id)
        statement = statement.order_by(Employee.full_name, Employee.id)
        rows, total = await self.employees.page(statement, page)
        departments = await self._departments({r.department_id for r in rows if r.department_id})
        return Page(
            items=[self._view(r, departments) for r in rows],
            total=total,
            page=page.page,
            page_size=page.page_size,
        )

    async def get(self, employee_id: UUID) -> EmployeeView:
        row = await self.employees.get(employee_id)
        departments = await self._departments({row.department_id} if row.department_id else set())
        return self._view(row, departments)

    async def _check_refs(self, department_id: UUID | None, manager_id: UUID | None) -> None:
        if department_id is not None:
            found = await self.session.scalar(
                select(Department.id).where(
                    Department.tenant_id == self.scope.tenant_id, Department.id == department_id
                )
            )
            if found is None:
                raise ResourceNotFound
        if manager_id is not None:
            await self.employees.get(manager_id)

    async def create(self, data: EmployeeCreate) -> EmployeeView:
        self.scope.require("hr.write")
        if (data.salary is not None or data.salary_currency) and not self.scope.can("hr.sensitive"):
            raise BusinessRuleViolation("SENSITIVE_FIELD", "Compensation needs HR sensitive access")
        await self._check_refs(data.department_id, data.manager_id)
        row = await self.employees.add(self.employees.new(**data.model_dump()))
        await record(
            self.session,
            "employee.created",
            scope=self.scope,
            entity_type="employee",
            entity_id=row.id,
        )
        return await self.get(row.id)

    async def update(self, employee_id: UUID, data: EmployeeUpdate) -> EmployeeView:
        self.scope.require("hr.write")
        row = await self.employees.get(employee_id, for_update=True)
        changes = data.model_dump(exclude_unset=True)
        if {"salary", "salary_currency"} & set(changes) and not self.scope.can("hr.sensitive"):
            raise BusinessRuleViolation("SENSITIVE_FIELD", "Compensation needs HR sensitive access")
        if changes.get("manager_id") == employee_id:
            raise BusinessRuleViolation("INVALID_MANAGER", "An employee cannot manage themself")
        await self._check_refs(changes.get("department_id"), changes.get("manager_id"))
        nullable = {
            "email",
            "phone",
            "department_id",
            "manager_id",
            "salary",
            "salary_currency",
            "termination_date",
        }
        for field, value in changes.items():
            if value is not None or field in nullable:
                setattr(row, field, value)
        if row.status == "terminated" and row.termination_date is None:
            row.termination_date = date.today()
        await self.session.flush()
        await record(
            self.session,
            "employee.updated",
            scope=self.scope,
            entity_type="employee",
            entity_id=row.id,
            details={"fields": sorted(changes)},
        )
        return await self.get(row.id)

    async def headcount(self) -> Headcount:
        rows = await self.session.execute(
            select(Employee.status, func.count())
            .where(self.employees.predicate())
            .group_by(Employee.status)
        )
        counts = {s: int(n) for s, n in rows}
        departments = await self.session.execute(
            select(func.coalesce(Department.name, "Unassigned"), func.count())
            .select_from(Employee)
            .outerjoin(
                Department,
                (Department.id == Employee.department_id)
                & (Department.tenant_id == Employee.tenant_id),
            )
            .where(self.employees.predicate(), Employee.status != "terminated")
            .group_by(Department.name)
            .order_by(func.count().desc())
            .limit(20)
        )
        return Headcount(
            total=sum(counts.values()),
            active=counts.get("active", 0),
            on_leave=counts.get("on_leave", 0),
            terminated=counts.get("terminated", 0),
            by_department=[(str(n), int(c)) for n, c in departments],
        )
