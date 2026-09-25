from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, Pagination
from app.modules.audit.service import record
from app.modules.business_settings.service import get_settings_row
from app.modules.customers.models import Customer
from app.modules.customers.service import log_activity
from app.modules.sales.models import SalesLead
from app.modules.sales.schemas import LeadCreate, LeadListItem, LeadUpdate, PipelineStage
from app.shared.money import quantize
from app.shared.scope import WorkspaceScope
from app.shared.state_machine import StateMachine
from app.shared.workspace_repository import WorkspaceRepository, like_pattern

LEAD_STAGES = StateMachine(
    "lead",
    {
        "new": frozenset({"qualified", "lost"}),
        "qualified": frozenset({"proposal", "lost", "new"}),
        "proposal": frozenset({"won", "lost", "qualified"}),
        "won": frozenset(),
        "lost": frozenset({"new"}),
    },
)


class SalesService:
    def __init__(self, session: AsyncSession, scope: WorkspaceScope) -> None:
        self.session, self.scope = session, scope
        self.leads = WorkspaceRepository(session, SalesLead, scope)
        self.customers = WorkspaceRepository(session, Customer, scope)

    async def search(
        self, page: Pagination, stage: str | None = None, search: str | None = None
    ) -> Page[LeadListItem]:
        statement = self.leads.select()
        if stage:
            statement = statement.where(SalesLead.stage == stage)
        if search:
            pattern = like_pattern(search.strip())
            statement = statement.where(or_(SalesLead.title.ilike(pattern)))
        statement = statement.order_by(SalesLead.updated_at.desc(), SalesLead.id)
        rows, total = await self.leads.page(statement, page)
        ids = {r.customer_id for r in rows if r.customer_id}
        names: dict[UUID, str] = {}
        if ids:
            result = await self.session.execute(
                select(Customer.id, Customer.name).where(
                    self.customers.predicate(), Customer.id.in_(ids)
                )
            )
            names = {i: n for i, n in result}
        items = [
            LeadListItem.model_validate(
                {
                    **{f: getattr(r, f) for f in LeadListItem.model_fields if hasattr(r, f)},
                    "customer_name": names.get(r.customer_id) if r.customer_id else None,
                    "next_stages": LEAD_STAGES.next_states(r.stage),
                }
            )
            for r in rows
        ]
        return Page(items=items, total=total, page=page.page, page_size=page.page_size)

    async def pipeline(self) -> list[PipelineStage]:
        # Values in other currencies are counted but never added to workspace-currency totals.
        currency = (await get_settings_row(self.session, self.scope)).default_currency
        value = func.sum(SalesLead.estimated_value).filter(SalesLead.currency == currency)
        rows = await self.session.execute(
            select(SalesLead.stage, func.count(), func.coalesce(value, 0))
            .where(self.leads.predicate())
            .group_by(SalesLead.stage)
        )
        found = {stage: (int(n), quantize(Decimal(v))) for stage, n, v in rows}
        return [
            PipelineStage(
                stage=s,
                count=found.get(s, (0, Decimal("0.00")))[0],
                value=found.get(s, (0, Decimal("0.00")))[1],
            )
            for s in ("new", "qualified", "proposal", "won", "lost")
        ]

    async def get(self, lead_id: UUID) -> SalesLead:
        return await self.leads.get(lead_id)

    async def create(self, data: LeadCreate) -> SalesLead:
        self.scope.require("sales.write")
        if data.customer_id:
            await self.customers.get(data.customer_id)
        currency = (
            data.currency or (await get_settings_row(self.session, self.scope)).default_currency
        )
        lead = await self.leads.add(
            self.leads.new(**data.model_dump(exclude={"currency"}), currency=currency)
        )
        if lead.customer_id:
            await log_activity(
                self.session,
                self.scope,
                lead.customer_id,
                "lead",
                f"Lead: {lead.title}",
                "lead",
                lead.id,
            )
        await record(
            self.session,
            "sales.lead_created",
            scope=self.scope,
            entity_type="sales_lead",
            entity_id=lead.id,
        )
        return lead

    async def update(self, lead_id: UUID, data: LeadUpdate) -> SalesLead:
        self.scope.require("sales.write")
        lead = await self.leads.get(lead_id, for_update=True)
        changes = data.model_dump(exclude_unset=True)
        if changes.get("customer_id"):
            await self.customers.get(changes["customer_id"])
        for field in ("title", "customer_id", "estimated_value", "notes"):
            if field in changes and (changes[field] is not None or field != "title"):
                setattr(lead, field, changes[field])
        await self.session.flush()
        # updated_at is a server-side onupdate value; load it now, not lazily in the response.
        await self.session.refresh(lead, ["updated_at"])
        await record(
            self.session,
            "sales.lead_updated",
            scope=self.scope,
            entity_type="sales_lead",
            entity_id=lead.id,
            details={"fields": sorted(changes)},
        )
        return lead

    async def move(self, lead_id: UUID, stage: str) -> SalesLead:
        self.scope.require("sales.write")
        lead = await self.leads.get(lead_id, for_update=True)
        LEAD_STAGES.ensure(lead.stage, stage)
        previous, lead.stage = lead.stage, stage
        lead.closed_at = datetime.now(UTC) if stage in ("won", "lost") else None
        await self.session.flush()
        await self.session.refresh(lead, ["updated_at"])
        await record(
            self.session,
            "sales.lead_stage_changed",
            scope=self.scope,
            entity_type="sales_lead",
            entity_id=lead.id,
            details={"from": previous, "to": stage},
        )
        return lead

    async def upsert_requirement(
        self,
        customer_id: UUID,
        conversation_id: UUID,
        title: str,
        requirements: dict[str, Any],
        missing: list[str],
    ) -> SalesLead:
        """PI's structured requirement capture: one open lead per conversation."""
        self.scope.require("sales.write")
        await self.customers.get(customer_id)
        lead = await self.session.scalar(
            self.leads.select()
            .where(
                SalesLead.conversation_id == conversation_id,
                SalesLead.source == "pi",
                SalesLead.stage.in_(["new", "qualified"]),
            )
            .with_for_update()
        )
        if lead is None:
            currency = (await get_settings_row(self.session, self.scope)).default_currency
            lead = await self.leads.add(
                self.leads.new(
                    customer_id=customer_id,
                    title=title[:200],
                    source="pi",
                    currency=currency,
                    requirements=requirements,
                    missing_information=missing[:20],
                    conversation_id=conversation_id,
                )
            )
            await log_activity(
                self.session,
                self.scope,
                customer_id,
                "lead",
                f"Requirement captured: {title[:100]}",
                "lead",
                lead.id,
            )
            action = "sales.requirement_created"
        else:
            merged = {**lead.requirements, **{k: v for k, v in requirements.items() if v}}
            lead.requirements = merged
            lead.missing_information = missing[:20]
            action = "sales.requirement_updated"
        await self.session.flush()
        await self.session.refresh(lead, ["updated_at"])
        await record(
            self.session,
            action,
            scope=self.scope,
            entity_type="sales_lead",
            entity_id=lead.id,
            details={"fields": sorted(requirements), "missing": missing[:20]},
        )
        return lead
