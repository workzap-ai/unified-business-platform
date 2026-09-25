"""Employee self-onboarding: HR shares a single-use link, the new employee submits their
details, and HR approves (creating the employee record) or rejects.

Personal details (CNIC, father's name, address, emergency contacts, bank account, NTN,
reference, introduction) are encrypted at rest with the platform credential key and are
only decrypted for holders of `hr.sensitive`. The public link carries a random token; only
its SHA-256 digest is stored, so the database cannot be used to reconstruct links.
"""

import hashlib
import hmac
import re
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from sqlalchemy import CheckConstraint, Date, DateTime, Index, String, Text, Uuid, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import Settings
from app.core.pagination import Page, Pagination
from app.integrations.crypto import CredentialManager
from app.modules.audit.service import record
from app.modules.customers.schemas import normalize_phone
from app.modules.environments.models import Environment
from app.modules.hr.models import Employee
from app.modules.hr.service import EmploymentType, HRService
from app.modules.notifications.service import notify
from app.modules.tenants.models import Tenant
from app.shared.errors import BusinessRuleViolation, Conflict, ResourceNotFound
from app.shared.models import WorkspaceRow, scoped_fk, workspace_args
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

LINK_TTL_DEFAULT_DAYS = 7
STATUSES = ("pending", "submitted", "approved", "rejected", "revoked")


class EmployeeOnboarding(WorkspaceRow):
    __tablename__ = "employee_onboardings"
    __table_args__ = workspace_args(
        "employee_onboardings",
        scoped_fk("employee_onboardings", "employee_id", "employees"),
        CheckConstraint(
            "status IN ('pending', 'submitted', 'approved', 'rejected', 'revoked')",
            name="status",
        ),
        Index("uq_employee_onboardings_token_hash", "token_hash", unique=True),
        Index("ix_employee_onboardings_scope_status", "tenant_id", "environment_id", "status"),
    )
    token_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Optional hints HR fills in when creating the link (shown pre-filled on the form).
    invited_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    invited_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    invited_designation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_by_label: Mapped[str] = mapped_column(String(80))
    # Non-sensitive summary for lists; everything else lives in details_encrypted.
    full_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    designation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    date_of_joining: Mapped[date | None] = mapped_column(Date, nullable=True)
    job_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    details_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    cnic_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    employee_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


# ---------------------------------------------------------------- input schemas

Text160 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=160)]
Text120 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)]
Optional80 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)]
JobType = Literal["onsite", "hybrid", "remote", "freelancer"]
Gender = Literal["male", "female"]

_CNIC = re.compile(r"^(\d{5})-?(\d{7})-?(\d)$")
_ACCOUNT = re.compile(r"^[A-Z0-9]{6,34}$")
_NTN = re.compile(r"^[A-Z0-9-]{5,20}$")


def normalize_cnic(value: str) -> str:
    match = _CNIC.fullmatch(value.strip().replace(" ", ""))
    if not match:
        raise ValueError("Enter the 13-digit CNIC as 12345-1234567-1")
    return "-".join(match.groups())


def _phone(value: str) -> str:
    raw = value.strip()
    if raw.startswith("0") and not raw.startswith("00"):
        raw = "+92" + raw[1:]  # local Pakistani format 03xx-xxxxxxx
    normalized = normalize_phone(raw)
    if normalized is None:
        raise ValueError("Enter a phone number")
    return normalized


class EmergencyContact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Text160
    phone: str = Field(max_length=32)

    @field_validator("phone")
    @classmethod
    def _valid_phone(cls, value: str) -> str:
        return _phone(value)


class OnboardingSubmission(BaseModel):
    """The new-employee form. Field names are the API contract for the web form."""

    model_config = ConfigDict(extra="forbid")
    full_name: Text160  # as per CNIC
    father_name: Text160
    cnic: str = Field(max_length=20)
    email: EmailStr
    designation: Text120
    gender: Gender | None = None
    date_of_joining: date
    date_of_birth: date
    job_type: JobType
    contact_number: str = Field(max_length=32)
    emergency_contact_1: EmergencyContact
    emergency_contact_2: EmergencyContact
    address: Address  # current address with nearby landmark
    account_title: Optional80 | None = None
    bank_name: Optional80 | None = None
    bank_account_number: str | None = Field(default=None, max_length=40)
    ntn: str | None = Field(default=None, max_length=24)
    professional_reference: str | None = Field(default=None, max_length=500)
    about: str | None = Field(default=None, max_length=2000)

    @field_validator("cnic")
    @classmethod
    def _cnic(cls, value: str) -> str:
        return normalize_cnic(value)

    @field_validator("contact_number")
    @classmethod
    def _contact(cls, value: str) -> str:
        return _phone(value)

    @field_validator("bank_account_number")
    @classmethod
    def _account(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        compact = re.sub(r"[\s-]", "", value).upper()
        if not _ACCOUNT.fullmatch(compact):
            raise ValueError("Enter the account number or IBAN (letters and digits only)")
        return compact

    @field_validator("ntn")
    @classmethod
    def _ntn(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        compact = value.strip().upper().replace(" ", "")
        if not _NTN.fullmatch(compact):
            raise ValueError("Enter a valid NTN")
        return compact

    @field_validator("account_title", "bank_name", "professional_reference", "about")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def _dates(self) -> "OnboardingSubmission":
        today = date.today()
        age = (today - self.date_of_birth).days // 365
        if self.date_of_birth >= today or not 14 <= age <= 100:
            raise ValueError("Enter a valid date of birth")
        if not today - timedelta(days=3650) <= self.date_of_joining <= today + timedelta(days=366):
            raise ValueError("Enter a valid date of joining")
        if bool(self.bank_account_number) and not self.bank_name:
            raise ValueError("Add the bank name for this account")
        return self


class LinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invited_name: Text160 | None = None
    invited_email: EmailStr | None = None
    invited_designation: Text120 | None = None
    expires_in_days: int = Field(default=LINK_TTL_DEFAULT_DAYS, ge=1, le=30)


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employment_type: EmploymentType | None = None
    job_title: Text120 | None = None
    department_id: UUID | None = None
    manager_id: UUID | None = None
    note: str | None = Field(default=None, max_length=500)


class Rejection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(min_length=3, max_length=500)


# ---------------------------------------------------------------- views


class LinkCreated(BaseModel):
    id: UUID
    token: str  # shown once; the web app builds the shareable URL from it
    path: str
    expires_at: datetime


class OnboardingSummary(BaseModel):
    id: UUID
    status: str
    effective_status: str  # pending past expiry reads as "expired"
    invited_name: str | None
    invited_email: str | None
    invited_designation: str | None
    full_name: str | None
    email: str | None
    designation: str | None
    date_of_joining: date | None
    job_type: str | None
    expires_at: datetime
    created_by_label: str
    created_at: datetime
    submitted_at: datetime | None
    reviewed_at: datetime | None
    reviewed_by_label: str | None
    review_note: str | None
    employee_id: UUID | None


class OnboardingDetail(OnboardingSummary):
    details: dict[str, Any] | None
    sensitive_visible: bool
    duplicate_employee_id: UUID | None


class PublicForm(BaseModel):
    organization_name: str
    status: Literal["open", "submitted", "closed", "expired"]
    expires_at: datetime
    prefill: dict[str, str]


# ---------------------------------------------------------------- helpers

SENSITIVE_KEYS = ("cnic", "bank_account_number", "ntn")


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def cnic_hash(settings: Settings, cnic: str) -> str | None:
    key = settings.secrets_encryption_key
    if key is None or not key.get_secret_value():
        return None
    first = key.get_secret_value().split(",")[0].strip().encode()
    return hmac.new(first, f"cnic:{cnic}".encode(), hashlib.sha256).hexdigest()


def mask(key: str, value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return value
    if key == "cnic":
        return "•••••-•••••••-" + value[-1]
    return "•" * max(len(value) - 4, 2) + value[-4:]


def effective_status(row: EmployeeOnboarding, now: datetime | None = None) -> str:
    if row.status == "pending" and row.expires_at <= (now or datetime.now(UTC)):
        return "expired"
    return row.status


def summary(row: EmployeeOnboarding) -> OnboardingSummary:
    return OnboardingSummary(
        id=row.id,
        status=row.status,
        effective_status=effective_status(row),
        invited_name=row.invited_name,
        invited_email=row.invited_email,
        invited_designation=row.invited_designation,
        full_name=row.full_name,
        email=row.email,
        designation=row.designation,
        date_of_joining=row.date_of_joining,
        job_type=row.job_type,
        expires_at=row.expires_at,
        created_by_label=row.created_by_label,
        created_at=row.created_at,
        submitted_at=row.submitted_at,
        reviewed_at=row.reviewed_at,
        reviewed_by_label=row.reviewed_by_label,
        review_note=row.review_note,
        employee_id=row.employee_id,
    )


# ---------------------------------------------------------------- HR service


class OnboardingService:
    def __init__(self, session: AsyncSession, scope: WorkspaceScope, settings: Settings) -> None:
        self.session, self.scope, self.settings = session, scope, settings
        self.rows = WorkspaceRepository(session, EmployeeOnboarding, scope)
        self.employees = WorkspaceRepository(session, Employee, scope)
        self.crypto = CredentialManager(settings)

    async def create_link(self, data: LinkCreate) -> LinkCreated:
        self.scope.require("hr.write")
        if not self.crypto.configured:
            # Fail before sharing a link whose submission could not be stored safely.
            self.crypto.encrypt("")
        token = secrets.token_urlsafe(32)
        row = await self.rows.add(
            self.rows.new(
                token_hash=token_digest(token),
                expires_at=datetime.now(UTC) + timedelta(days=data.expires_in_days),
                invited_name=data.invited_name,
                invited_email=str(data.invited_email) if data.invited_email else None,
                invited_designation=data.invited_designation,
                created_by_user_id=self.scope.user_id,
                created_by_label=self.scope.actor_label[:80],
            )
        )
        await record(
            self.session,
            "employee_onboarding.link_created",
            scope=self.scope,
            entity_type="employee_onboarding",
            entity_id=row.id,
            details={"expires_in_days": data.expires_in_days},
        )
        return LinkCreated(
            id=row.id, token=token, path=f"/onboarding/{token}", expires_at=row.expires_at
        )

    async def search(self, page: Pagination, status: str | None) -> Page[OnboardingSummary]:
        self.scope.require("hr.write")
        now = datetime.now(UTC)
        conditions = []
        if status == "expired":
            conditions = [EmployeeOnboarding.status == "pending"]
            conditions.append(EmployeeOnboarding.expires_at <= now)
        elif status == "pending":
            conditions = [EmployeeOnboarding.status == "pending"]
            conditions.append(EmployeeOnboarding.expires_at > now)
        elif status:
            conditions = [EmployeeOnboarding.status == status]
        statement = (
            self.rows.select()
            .where(*conditions)
            .order_by(EmployeeOnboarding.created_at.desc(), EmployeeOnboarding.id)
        )
        rows, total = await self.rows.page(statement, page)
        return Page(
            items=[summary(r) for r in rows],
            total=total,
            page=page.page,
            page_size=page.page_size,
        )

    async def detail(self, onboarding_id: UUID) -> OnboardingDetail:
        self.scope.require("hr.write")
        row = await self.rows.get(onboarding_id)
        sensitive = self.scope.can("hr.sensitive")
        details: dict[str, Any] | None = None
        if row.details_encrypted:
            details = self.crypto.decrypt_json(row.details_encrypted)
            if not sensitive:
                details = {k: mask(k, v) if k in SENSITIVE_KEYS else v for k, v in details.items()}
        duplicate = None
        if row.cnic_hash and row.status == "submitted":
            duplicate = await self.employees.find(Employee.cnic_hash == row.cnic_hash)
        return OnboardingDetail(
            **summary(row).model_dump(),
            details=details,
            sensitive_visible=sensitive,
            duplicate_employee_id=duplicate.id if duplicate else None,
        )

    async def approve(self, onboarding_id: UUID, data: Approval) -> OnboardingDetail:
        self.scope.require("hr.write")
        row = await self.rows.get(onboarding_id, for_update=True)
        if row.status != "submitted" or not row.details_encrypted:
            raise BusinessRuleViolation(
                "ONBOARDING_NOT_SUBMITTED", "Only submitted forms can be approved"
            )
        if row.cnic_hash and await self.employees.find(Employee.cnic_hash == row.cnic_hash):
            raise Conflict("An employee with this CNIC already exists")
        details = self.crypto.decrypt_json(row.details_encrypted)
        employment_type = data.employment_type or (
            "contract" if details["job_type"] == "freelancer" else "full_time"
        )
        hr = HRService(self.session, self.scope)
        await hr._check_refs(data.department_id, data.manager_id)
        personal = {
            k: details.get(k)
            for k in (
                "father_name",
                "cnic",
                "address",
                "emergency_contact_1",
                "emergency_contact_2",
                "account_title",
                "bank_name",
                "bank_account_number",
                "ntn",
                "professional_reference",
                "about",
            )
        }
        employee = await self.employees.add(
            self.employees.new(
                full_name=details["full_name"],
                email=details["email"],
                phone=details["contact_number"],
                job_title=data.job_title or details["designation"],
                department_id=data.department_id,
                manager_id=data.manager_id,
                employment_type=employment_type,
                hire_date=date.fromisoformat(details["date_of_joining"]),
                gender=details.get("gender"),
                date_of_birth=date.fromisoformat(details["date_of_birth"]),
                work_arrangement=details["job_type"],
                personal_details_encrypted=self.crypto.encrypt_json(personal),
                cnic_hash=row.cnic_hash,
            )
        )
        row.status, row.employee_id = "approved", employee.id
        row.reviewed_at, row.reviewed_by_label = datetime.now(UTC), self.scope.actor_label[:80]
        row.review_note = data.note
        await self.session.flush()
        await record(
            self.session,
            "employee_onboarding.approved",
            scope=self.scope,
            entity_type="employee_onboarding",
            entity_id=row.id,
            details={"employee_id": str(employee.id)},
        )
        await record(
            self.session,
            "employee.created",
            scope=self.scope,
            entity_type="employee",
            entity_id=employee.id,
            details={"source": "onboarding"},
        )
        return await self.detail(row.id)

    async def reject(self, onboarding_id: UUID, data: Rejection) -> OnboardingDetail:
        self.scope.require("hr.write")
        row = await self.rows.get(onboarding_id, for_update=True)
        if row.status != "submitted":
            raise BusinessRuleViolation(
                "ONBOARDING_NOT_SUBMITTED", "Only submitted forms can be rejected"
            )
        row.status = "rejected"
        row.reviewed_at, row.reviewed_by_label = datetime.now(UTC), self.scope.actor_label[:80]
        row.review_note = data.note
        await self.session.flush()
        await record(
            self.session,
            "employee_onboarding.rejected",
            scope=self.scope,
            entity_type="employee_onboarding",
            entity_id=row.id,
        )
        return await self.detail(row.id)

    async def revoke(self, onboarding_id: UUID) -> OnboardingDetail:
        self.scope.require("hr.write")
        row = await self.rows.get(onboarding_id, for_update=True)
        if row.status != "pending":
            raise BusinessRuleViolation(
                "ONBOARDING_NOT_PENDING", "Only unused links can be revoked"
            )
        row.status = "revoked"
        await self.session.flush()
        await record(
            self.session,
            "employee_onboarding.revoked",
            scope=self.scope,
            entity_type="employee_onboarding",
            entity_id=row.id,
        )
        return await self.detail(row.id)

    async def personal_details(self, employee_id: UUID) -> dict[str, Any]:
        self.scope.require("hr.sensitive")
        employee = await self.employees.get(employee_id)
        return self.crypto.decrypt_json(employee.personal_details_encrypted)


# ---------------------------------------------------------------- public form


class PublicOnboarding:
    """Token-authenticated access for the person completing the form (no session)."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session, self.settings = session, settings

    async def _find(self, token: str, for_update: bool = False) -> EmployeeOnboarding:
        if not 20 <= len(token) <= 128:
            raise ResourceNotFound
        query = select(EmployeeOnboarding).where(
            EmployeeOnboarding.token_hash == token_digest(token),
            select(Tenant.id)
            .where(Tenant.id == EmployeeOnboarding.tenant_id, Tenant.status == "active")
            .exists(),
            select(Environment.id)
            .where(
                Environment.id == EmployeeOnboarding.environment_id,
                Environment.tenant_id == EmployeeOnboarding.tenant_id,
                Environment.status == "active",
            )
            .exists(),
        )
        if for_update:
            query = query.with_for_update()
        row = await self.session.scalar(query)
        if row is None:
            raise ResourceNotFound
        return row

    async def form(self, token: str) -> PublicForm:
        row = await self._find(token)
        name = await self.session.scalar(select(Tenant.name).where(Tenant.id == row.tenant_id))
        state = effective_status(row)
        status: Literal["open", "submitted", "closed", "expired"] = (
            "open"
            if state == "pending"
            else "expired"
            if state == "expired"
            else "submitted"
            if state in ("submitted", "approved")
            else "closed"
        )
        prefill = {
            k: v
            for k, v in (
                ("full_name", row.invited_name),
                ("email", row.invited_email),
                ("designation", row.invited_designation),
            )
            if v and status == "open"
        }
        return PublicForm(
            organization_name=name or "", status=status, expires_at=row.expires_at, prefill=prefill
        )

    async def submit(
        self, token: str, data: OnboardingSubmission, request_id: str | None
    ) -> PublicForm:
        row = await self._find(token, for_update=True)
        if effective_status(row) != "pending":
            raise BusinessRuleViolation(
                "ONBOARDING_LINK_CLOSED", "This onboarding link is no longer accepting responses"
            )
        crypto = CredentialManager(self.settings)
        values = data.model_dump(mode="json")
        row.details_encrypted = crypto.encrypt_json(values)
        row.cnic_hash = cnic_hash(self.settings, data.cnic)
        row.full_name, row.email = data.full_name, str(data.email)
        row.designation, row.date_of_joining = data.designation, data.date_of_joining
        row.job_type, row.status = data.job_type, "submitted"
        row.submitted_at = datetime.now(UTC)
        await self.session.flush()
        scope = WorkspaceScope.system(
            row.tenant_id,
            row.environment_id,
            frozenset({"hr.write"}),
            "Onboarding form",
            request_id,
        )
        await record(
            self.session,
            "employee_onboarding.submitted",
            scope=scope,
            entity_type="employee_onboarding",
            entity_id=row.id,
        )
        await notify(
            self.session,
            scope,
            "hr",
            f"Onboarding form submitted: {data.full_name}",
            f"{data.full_name} ({data.designation}) completed their details. Review and approve.",
            link=f"/hr/onboarding/{row.id}",
            permission="hr.write",
            dedupe_key=f"onboarding-submitted:{row.id}",
        )
        return await self.form(token)
