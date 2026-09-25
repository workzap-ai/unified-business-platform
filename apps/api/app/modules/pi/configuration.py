from copy import deepcopy
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.audit.service import record
from app.modules.pi.models import AGENT_KEYS, PiAgent, PiAgentVersion, PiSettings
from app.modules.pi.tools.catalog import TOOL_CATALOG
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

DEFAULTS: dict[str, Any] = {
    "auto_reply_enabled": True,
    "timezone": "UTC",
    "business_hours": {
        "enabled": False,
        "days": {
            day: {"open": True, "start": "09:00", "end": "17:00"}
            for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
        },
        "outside_hours": "handoff_only",
        "notice": "Our team will follow up during business hours.",
    },
    "response_rules": {
        "language": "auto",
        "max_reply_chars": 4000,
        "tone": "friendly",
        "greeting": "Hello! How can we help?",
        "sign_off": "",
    },
    "ai_config": {
        "router_alias": "fast",
        "reply_alias": "balanced",
        "temperature": "0.20",
        "clarify_before_handoff": 1,
    },
    "tool_permissions": {key: True for key in TOOL_CATALOG},
    "handoff_rules": {
        "keywords": ["human", "representative"],
        "low_confidence_threshold": "0.75",
        "max_failed_turns": 2,
        "handoff_on_complaint": True,
        "notify_roles": ["owner", "support"],
    },
    "knowledge_config": {
        "top_k": 5,
        "min_score": "0.30",
        "semantic_enabled": False,
        "cite_sources_to_operators": True,
    },
    "whatsapp_config": {
        "send_read_receipts": False,
        "typing_indicator": False,
        "media_voice": False,
        "media_images": False,
        "max_media_mb": 10,
    },
}


class VersionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instructions: str = Field(default="", max_length=4000)
    model_alias: str = Field(pattern=r"^(fast|balanced|reasoning)$")
    temperature: Decimal = Field(ge=0, le=1, max_digits=3, decimal_places=2)
    note: str = Field(default="", max_length=200)


async def settings_row(session: AsyncSession, scope: WorkspaceScope) -> PiSettings:
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
    if isinstance(value, dict):
        if set(value) - set(default):
            raise BusinessRuleViolation("INVALID_SETTING", "Unknown setting fields")
        value = {**default, **value}
        for key, item in value.items():
            if type(item) is not type(default[key]):
                raise BusinessRuleViolation("INVALID_SETTING", "Invalid setting value")
    if section == "timezone":
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise BusinessRuleViolation("INVALID_TIMEZONE", "Choose a valid timezone") from None
    if section == "response_rules" and not 100 <= value["max_reply_chars"] <= 4000:
        raise BusinessRuleViolation("INVALID_SETTING", "Reply limit must be between 100 and 4000")
    from app.modules.pi.policy import validate_section

    validate_section(section, value)
    row = await settings_row(session, scope)
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
    for key in AGENT_KEYS:
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
