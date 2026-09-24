from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, ForeignKeyConstraint, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, scoped_fk, workspace_args
from app.shared.money import MONEY_SQL


class Employee(WorkspaceRow):
    __tablename__ = "employees"
    __table_args__ = workspace_args(
        "employees",
        ForeignKeyConstraint(
            ["tenant_id", "department_id"],
            ["departments.tenant_id", "departments.id"],
            ondelete="RESTRICT",
            name="fk_employees_department",
        ),
        scoped_fk("employees", "manager_id", "employees"),
        CheckConstraint(
            "employment_type IN ('full_time', 'part_time', 'contract', 'intern')",
            name="employment_type",
        ),
        CheckConstraint("status IN ('active', 'on_leave', 'terminated')", name="status"),
        CheckConstraint("salary IS NULL OR salary >= 0", name="salary_nonnegative"),
        CheckConstraint(
            "termination_date IS NULL OR termination_date >= hire_date", name="dates_ordered"
        ),
        CheckConstraint("manager_id IS NULL OR manager_id <> id", name="not_own_manager"),
        Index("ix_employees_scope_status", "tenant_id", "environment_id", "status"),
        Index("ix_employees_department", "tenant_id", "department_id"),
    )
    full_name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(16), nullable=True)
    job_title: Mapped[str] = mapped_column(String(120))
    department_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    manager_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    employment_type: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    hire_date: Mapped[date] = mapped_column(Date)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Sensitive: only returned to holders of hr.sensitive.
    salary: Mapped[Decimal | None] = mapped_column(MONEY_SQL, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
