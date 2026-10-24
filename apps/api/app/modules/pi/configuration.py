from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import event, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.audit.service import record
from app.modules.pi.models import AGENT_KEYS, PiAgent, PiAgentVersion, PiSettings
from app.modules.pi.tools.catalog import TOOL_CATALOG
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

OPT_IN_TOOLS = frozenset(
    {
        "check_availability",
        "create_booking",
        "cancel_booking",
        "get_bookings",
        "create_task",
        "create_ticket",
        "get_project_status",
        "request_payment",
        "get_payment_status",
        "reschedule_booking",
        "email_booking_confirmation",
        "send_form",
        "get_store_orders",
    }
)

DEFAULTS: dict[str, Any] = {
    "auto_reply_enabled": True,
    "timezone": "UTC",
    "business_hours": {
        "enabled": False,
        "days": {
            day: {"open": True, "start": "09:00", "end": "17:00"}
            for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
        },
        "outside_hours": "reply_with_notice",
        "notice": "Our team will follow up during business hours.",
    },
    "response_rules": {
        "language": "auto",
        "max_reply_chars": 4000,
        "tone": "friendly",
        "greeting": "Hello! How can we help?",
        "sign_off": "",
        "service_mode": "auto",
        # "" = automatic (services never publish prices; products quote approved prices).
        "price_disclosure": "",
        # ai_led | mixed | human_approved (see tools.handlers._delivery_status).
        "execution_mode": "ai_led",
        "staff_summary_language": "en",
        # pi's constitution as a reply linter (pi Brain spec Parts 1, 2, 6): AI disclosure, one
        # short question, no hype, no money or identity slips. Off until a workspace opts in.
        "constitution": False,
        # "brain" = Workzap's own pi flow (pi Brain spec): a conversation state machine, the
        # constitution linter and listening-first rules. "standard" = the shared flow.
        "pi_mode": "standard",
        # Tunable numbers inside their tested ranges and the learning switch (brain_config.py,
        # learning.frozen). Empty = every default; learning stays frozen until set to False.
        "brain": {},
    },
    "ai_config": {
        "router_alias": "fast",
        "reply_alias": "balanced",
        "temperature": "0.20",
        "clarify_before_handoff": 1,
    },
    # Tools added after launch are opt-in, so existing workspaces never start creating
    # bookings, tasks or tickets without choosing to.
    "tool_permissions": {key: key not in OPT_IN_TOOLS for key in TOOL_CATALOG},
    "handoff_rules": {
        "keywords": ["human", "representative"],
        "low_confidence_threshold": "0.75",
        "max_failed_turns": 2,
        "handoff_on_complaint": True,
        "notify_roles": ["owner", "support"],
        # Where each customer problem belongs. Pi sorts problems into these; the team
        # can move one, and those moves become examples Pi learns from.
        "departments": [
            {
                "key": "sales",
                "name": "Sales",
                "description": "New enquiries, quotes, prices and orders not yet placed.",
            },
            {
                "key": "customer_support",
                "name": "Customer support",
                "description": "Help with a product or service the customer already has.",
            },
            {
                "key": "finance",
                "name": "Finance",
                "description": "Payments, invoices, refunds, balances and billing problems.",
            },
            {
                "key": "delivery",
                "name": "Delivery",
                "description": "Shipping, delivery dates, tracking and returns.",
            },
            {
                "key": "operations",
                "name": "Operations / Manufacturing",
                "description": "Production, quality, stock, materials and custom work.",
            },
            {
                "key": "it",
                "name": "IT / Technical",
                "description": "Websites, apps, software, logins and technical faults.",
            },
            {
                "key": "hr",
                "name": "HR",
                "description": "Jobs, hiring, staff and workplace questions.",
            },
        ],
        "department_examples": [],
    },
    "knowledge_config": {
        "top_k": 5,
        "min_score": "0.30",
        "semantic_enabled": False,
        "cite_sources_to_operators": True,
        # Industry knowledge packs: pi learns how the customer's trade talks and what to
        # listen for (pi Brain spec, Part 7). Off until a workspace turns it on.
        "industry_packs": False,
    },
    "whatsapp_config": {
        "send_read_receipts": False,
        "typing_indicator": False,
        "media_voice": True,
        "media_images": True,
        "media_video": True,
        "max_media_mb": 10,
        "reminder_enabled": True,
        "reminder_after_days": 7,
        # A free-form check-in when a customer goes quiet mid-conversation (24h window).
        "check_in_enabled": True,
        "check_in_after_hours": 2,
        # After asking once in the chat, pi sends the Business details form.
        "business_form": True,
        "reminder_templates": {},
        # Follow-up ladder after the 24-hour window: {"en": {"day3": {name, language}, ...}}.
        "ladder_templates": {},
        # pi Customer's sign-in code after the 24-hour window: Meta's authentication
        # template {name, language} ({} until "Auto follow-ups" sets it up).
        "code_template": {},
        # A meeting's time and link after the 24-hour window: Meta's approved Utility
        # templates {"en": {name, language, status}} ("Auto follow-ups" sets them up).
        "meeting_templates": {},
        "follow_up_ladder": True,
        # pi's picture cards (Problem Map, journey) on WhatsApp.
        "visual_cards": True,
        # PDFs, Word, Excel and PowerPoint files pi reads.
        "media_documents": True,
        # No reminders between these local hours (start == end turns quiet hours off).
        "quiet_start": 21,
        "quiet_end": 9,
        # WhatsApp Flows the business published: {"lead": {"flow_id", "cta", "screen"}}.
        "flows": {},
        # PI Customer: customers can see their own conversations with this business.
        "customer_portal": True,
        # Team board alerts on WhatsApp (pi_saas/team_alerts.py): members' numbers,
        # on/off and an optional approved template. Edited on the team board.
        "team_alerts": {},
    },
}


class VersionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instructions: str = Field(default="", max_length=4000)
    model_alias: str = Field(pattern=r"^(fast|balanced|reasoning)$")
    temperature: Decimal = Field(ge=0, le=1, max_digits=3, decimal_places=2)
    note: str = Field(default="", max_length=200)


_TURN_CACHE = "pi_settings_turn_cache"


@asynccontextmanager
async def settings_cache_for_turn(session: AsyncSession) -> AsyncIterator[None]:
    """Let `settings_row` answer from memory between two commits of this session.

    A pi turn asks for the settings about eight times (each call was an upsert plus a read, two
    round trips to a remote database). Inside this block the first call reads them and later
    calls return the same row until the session commits or rolls back, which is exactly when a
    fresh read could see anything new. Only the turn runner uses it; every other caller, and any
    code after the block, keeps reading every time."""
    cache: dict[tuple[UUID, UUID], PiSettings] = {}
    session.info[_TURN_CACHE] = cache

    def clear(_session: Any, *_: Any) -> None:
        cache.clear()

    for name in ("after_commit", "after_rollback"):
        event.listen(session.sync_session, name, clear)
    try:
        yield
    finally:
        for name in ("after_commit", "after_rollback"):
            event.remove(session.sync_session, name, clear)
        session.info.pop(_TURN_CACHE, None)


async def settings_row(session: AsyncSession, scope: WorkspaceScope) -> PiSettings:
    cache: dict[tuple[UUID, UUID], PiSettings] | None = session.info.get(_TURN_CACHE)
    key = (scope.tenant_id, scope.environment_id)
    if cache is not None and key in cache:
        return cache[key]
    row = await _read_settings_row(session, scope)
    if cache is not None:
        cache[key] = row
    return row


async def _read_settings_row(session: AsyncSession, scope: WorkspaceScope) -> PiSettings:
    values = deepcopy(DEFAULTS)
    values["provider_config"] = {}
    await session.execute(
        insert(PiSettings)
        .values(tenant_id=scope.tenant_id, environment_id=scope.environment_id, **values)
        .on_conflict_do_nothing(constraint="uq_pi_settings_scope")
    )
    row = await session.scalar(
        WorkspaceRepository(session, PiSettings, scope)
        .select()
        .execution_options(populate_existing=True)
    )
    assert row is not None
    # New settings are available to existing workspaces without overwriting their choices.
    for key, defaults in DEFAULTS.items():
        if isinstance(defaults, dict):
            setattr(row, key, {**deepcopy(defaults), **getattr(row, key)})
    return row


async def settings_view(
    session: AsyncSession, scope: WorkspaceScope, settings: Settings
) -> dict[str, Any]:
    row = await settings_row(session, scope)
    result = {key: getattr(row, key) for key in DEFAULTS}
    result["provider_config"] = {
        "order": settings.provider_order(),
        "retry_transient": settings.llm_max_retries > 0,
        "max_retries": settings.llm_max_retries,
        "timeout_seconds": settings.llm_timeout_seconds,
    }
    result["permissions"] = [
        {
            "role": "Current member",
            "view_inbox": scope.can("pi.read"),
            "reply": scope.can("pi.inbox.reply"),
            "takeover": scope.can("pi.inbox.reply"),
            "configure": scope.can("pi.settings.manage"),
        }
    ]
    return result


async def update_settings(
    session: AsyncSession, scope: WorkspaceScope, section: str, value: Any
) -> None:
    scope.require("pi.settings.manage")
    if section not in DEFAULTS:
        raise BusinessRuleViolation(
            "SERVER_CONFIGURATION", "This setting is managed by the deployment operator"
        )
    default = DEFAULTS[section]
    if type(value) is not type(default):
        raise BusinessRuleViolation("INVALID_SETTING", "Invalid setting value")
    row = await settings_row(session, scope)
    if isinstance(value, dict):
        if set(value) - set(default):
            raise BusinessRuleViolation("INVALID_SETTING", "Unknown setting fields")
        # Fields a form didn't send keep their saved value (not the default), so a
        # screen that edits part of a section never wipes the rest.
        saved = getattr(row, section, None)
        value = {**default, **(saved if isinstance(saved, dict) else {}), **value}
        # A field saved before it had a default (an older or newer screen) never breaks
        # a save; fields with a default must keep its type.
        for key, item in value.items():
            if key in default and type(item) is not type(default[key]):
                raise BusinessRuleViolation("INVALID_SETTING", "Invalid setting value")
    if section == "timezone":
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise BusinessRuleViolation("INVALID_TIMEZONE", "Choose a valid timezone") from None
    if section == "response_rules" and not 100 <= value["max_reply_chars"] <= 4000:
        raise BusinessRuleViolation("INVALID_SETTING", "Reply limit must be between 100 and 4000")
    if section == "handoff_rules":
        # Examples taught for a department that was removed are dropped with it.
        keys = {d.get("key") for d in value.get("departments", []) if isinstance(d, dict)}
        value["department_examples"] = [
            e
            for e in value.get("department_examples", [])
            if isinstance(e, dict) and e.get("department") in keys
        ]
    from app.modules.pi.policy import validate_section

    validate_section(section, value)
    setattr(row, section, value)
    await session.flush()
    await record(
        session,
        "pi.settings_updated",
        scope=scope,
        entity_type="pi_settings",
        entity_id=row.id,
        details={"section": section},
    )


async def seed_agents(session: AsyncSession, scope: WorkspaceScope) -> None:
    # One read of what exists, then an insert only for what is missing (was one insert per key,
    # every turn). The insert keeps its ON CONFLICT guard for a concurrent first turn.
    existing = set(
        await session.scalars(
            select(PiAgent.key).where(WorkspaceRepository(session, PiAgent, scope).predicate())
        )
    )
    for key in AGENT_KEYS:
        if key in existing:
            continue
        agent_id = await session.scalar(
            insert(PiAgent)
            .values(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                key=key,
                name=key.replace("_", " ").title(),
                description=f"Controlled {key.replace('_', ' ')} workflow",
            )
            .on_conflict_do_nothing(constraint="uq_pi_agents_key")
            .returning(PiAgent.id)
        )
        if agent_id:
            session.add(
                PiAgentVersion(
                    tenant_id=scope.tenant_id,
                    environment_id=scope.environment_id,
                    agent_id=agent_id,
                    version=1,
                    instructions="",
                    model_alias="fast",
                    temperature=Decimal("0.20"),
                    created_by_label="System",
                )
            )
    await session.flush()


async def publish(
    session: AsyncSession, scope: WorkspaceScope, agent_id: UUID, data: VersionInput
) -> PiAgentVersion:
    scope.require("pi.agents.manage")
    agent = await WorkspaceRepository(session, PiAgent, scope).get(agent_id, for_update=True)
    agent.current_version += 1
    version = await WorkspaceRepository(session, PiAgentVersion, scope).add(
        PiAgentVersion(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            agent_id=agent.id,
            version=agent.current_version,
            created_by_label=scope.actor_label,
            **data.model_dump(),
        )
    )
    await record(
        session,
        "pi.agent_published",
        scope=scope,
        entity_type="pi_agent",
        entity_id=agent.id,
        details={"version": version.version},
    )
    return version
