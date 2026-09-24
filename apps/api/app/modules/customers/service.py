from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, Pagination
from app.modules.audit.service import record
from app.modules.customers.models import Customer, CustomerActivity, CustomerNote
from app.modules.customers.schemas import (
    ActivityView,
    CustomerCreate,
    CustomerUpdate,
    CustomerView,
    NoteView,
    normalize_phone,
)
from app.shared.errors import Conflict
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository, like_pattern, to_page


async def log_activity(
    session: AsyncSession,
    scope: WorkspaceScope,
    customer_id: UUID,
    kind: str,
    summary: str,
    ref_type: str | None = None,
    ref_id: UUID | None = None,
) -> None:
    """Cross-module interface: other modules append to the customer timeline here."""
    session.add(
        CustomerActivity(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            customer_id=customer_id,
            kind=kind,
            summary=summary[:240],
            ref_type=ref_type,
            ref_id=ref_id,
            actor_label=scope.actor_label[:80],
        )
    )
    await session.flush()


class CustomerService:
    def __init__(self, session: AsyncSession, scope: WorkspaceScope) -> None:
        self.session, self.scope = session, scope
        self.customers = WorkspaceRepository(session, Customer, scope)
        self.notes = WorkspaceRepository(session, CustomerNote, scope)
        self.activities = WorkspaceRepository(session, CustomerActivity, scope)

    async def search(
        self,
        page: Pagination,
        search: str | None = None,
        status: str | None = None,
        tag: str | None = None,
    ) -> Page[CustomerView]:
        statement = self.customers.select()
        if search:
            pattern = like_pattern(search.strip())
            statement = statement.where(
                or_(
                    Customer.name.ilike(pattern),
                    Customer.email.ilike(pattern),
                    Customer.phone.ilike(pattern),
                    Customer.company.ilike(pattern),
                )
            )
        if status:
            statement = statement.where(Customer.status == status)
        if tag:
            statement = statement.where(Customer.tags.contains([tag.strip().lower()]))
        statement = statement.order_by(Customer.created_at.desc(), Customer.id)
        rows, total = await self.customers.page(statement, page)
        return to_page(CustomerView, rows, total, page)

    async def get(self, customer_id: UUID) -> Customer:
        return await self.customers.get(customer_id)

    async def create(self, data: CustomerCreate, source: str = "manual") -> Customer:
        self.scope.require("customers.write")
        values = data.model_dump()
        values["tags"] = sorted(set(values["tags"]))
        try:
            async with self.session.begin_nested():
                customer = await self.customers.add(self.customers.new(source=source, **values))
        except IntegrityError:
            raise Conflict("A customer with this phone number already exists") from None
        await log_activity(
            self.session, self.scope, customer.id, "created", "Customer created", "customer"
        )
        await record(
            self.session,
            "customer.created",
            scope=self.scope,
            entity_type="customer",
            entity_id=customer.id,
            details={"source": source},
        )
        return customer

    async def update(self, customer_id: UUID, data: CustomerUpdate) -> Customer:
        self.scope.require("customers.write")
        customer = await self.customers.get(customer_id, for_update=True)
        changes = data.model_dump(exclude_unset=True)
        if "tags" in changes and changes["tags"] is not None:
            changes["tags"] = sorted(set(changes["tags"]))
        allowed = {"name", "email", "phone", "company", "tags"}
        for field, value in changes.items():
            if field in allowed and not (field == "name" and value is None):
                setattr(customer, field, value)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError:
            raise Conflict("A customer with this phone number already exists") from None
        await log_activity(
            self.session, self.scope, customer.id, "updated", "Customer details updated"
        )
        await record(
            self.session,
            "customer.updated",
            scope=self.scope,
            entity_type="customer",
            entity_id=customer.id,
            details={"fields": sorted(changes)},
        )
        return customer

    async def set_status(self, customer_id: UUID, status: str) -> Customer:
        self.scope.require("customers.write")
        customer = await self.customers.get(customer_id, for_update=True)
        customer.status = status
        await self.session.flush()
        await record(
            self.session,
            f"customer.{'archived' if status == 'archived' else 'restored'}",
            scope=self.scope,
            entity_type="customer",
            entity_id=customer.id,
        )
        return customer

    async def add_note(self, customer_id: UUID, body: str) -> CustomerNote:
        self.scope.require("customers.write")
        await self.customers.get(customer_id)
        note = await self.notes.add(
            self.notes.new(
                customer_id=customer_id,
                author_user_id=self.scope.user_id,
                author_label=self.scope.actor_label[:80],
                body=body,
            )
        )
        await log_activity(
            self.session, self.scope, customer_id, "note", body[:120], "note", note.id
        )
        return note

    async def notes_page(self, customer_id: UUID, page: Pagination) -> Page[NoteView]:
        await self.customers.get(customer_id)
        statement = (
            self.notes.select()
            .where(CustomerNote.customer_id == customer_id)
            .order_by(CustomerNote.created_at.desc(), CustomerNote.id)
        )
        rows, total = await self.notes.page(statement, page)
        return to_page(NoteView, rows, total, page)

    async def activities_page(self, customer_id: UUID, page: Pagination) -> Page[ActivityView]:
        await self.customers.get(customer_id)
        statement = (
            self.activities.select()
            .where(CustomerActivity.customer_id == customer_id)
            .order_by(CustomerActivity.created_at.desc(), CustomerActivity.id)
        )
        rows, total = await self.activities.page(statement, page)
        return to_page(ActivityView, rows, total, page)

    async def by_ids(self, ids: Sequence[UUID]) -> dict[UUID, Customer]:
        if not ids:
            return {}
        rows = await self.session.scalars(self.customers.select().where(Customer.id.in_(ids)))
        return {c.id: c for c in rows}

    async def resolve_whatsapp(self, wa_id: str, profile_name: str | None) -> tuple[Customer, bool]:
        """Find the customer for a WhatsApp sender in this workspace, creating one if new."""
        digits = "".join(ch for ch in wa_id if ch.isdigit())[:15]
        phone = normalize_phone("+" + digits)
        existing = await self.customers.find(
            or_(Customer.whatsapp_id == digits, Customer.phone == phone)
        )
        if existing is not None:
            if existing.whatsapp_id is None:
                existing.whatsapp_id = digits
            existing.last_contacted_at = datetime.now(UTC)
            await self.session.flush()
            return existing, False
        name = (profile_name or "").strip()[:160] or f"WhatsApp {phone}"
        try:
            async with self.session.begin_nested():
                customer = await self.customers.add(
                    self.customers.new(
                        name=name,
                        phone=phone,
                        whatsapp_id=digits,
                        source="whatsapp",
                        tags=[],
                        last_contacted_at=datetime.now(UTC),
                    )
                )
        except IntegrityError:
            # A concurrent message created it first; use that record.
            found = await self.customers.find(Customer.whatsapp_id == digits)
            if found is None:
                raise
            return found, False
        await log_activity(
            self.session, self.scope, customer.id, "created", "Customer created from WhatsApp"
        )
        await record(
            self.session,
            "customer.created",
            scope=self.scope,
            entity_type="customer",
            entity_id=customer.id,
            details={"source": "whatsapp"},
        )
        return customer, True
