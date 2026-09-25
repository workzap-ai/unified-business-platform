from datetime import UTC, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from app.modules.pi.models import PiSettings
from app.shared.errors import BusinessRuleViolation


def ensure(condition: bool) -> None:
    if not condition:
        raise ValueError("Invalid configuration")


def validate_section(section: str, value: Any) -> None:
    try:
        if section == "business_hours":
            ensure(value["outside_hours"] in {"reply", "reply_with_notice", "handoff_only"})
            ensure(set(value["days"]) == {"mon", "tue", "wed", "thu", "fri", "sat", "sun"})
            for day in value["days"].values():
                ensure(set(day) == {"open", "start", "end"} and type(day["open"]) is bool)
                ensure(time.fromisoformat(day["start"]) < time.fromisoformat(day["end"]))
            ensure(len(value["notice"]) <= 1000)
        if section == "response_rules":
            ensure(value["language"] in {"auto", "en", "ur", "roman_ur"})
            ensure(value["tone"] in {"friendly", "formal", "concise"})
            ensure(len(value["greeting"]) <= 2000 and len(value["sign_off"]) <= 200)
        if section == "ai_config":
            ensure(value["router_alias"] in {"fast", "balanced"})
            ensure(value["reply_alias"] in {"fast", "balanced", "reasoning"})
            ensure(0 <= Decimal(value["temperature"]) <= 1)
            ensure(0 <= value["clarify_before_handoff"] <= 3)
        if section == "handoff_rules":
            ensure(0 <= Decimal(value["low_confidence_threshold"]) <= 1)
            ensure(1 <= value["max_failed_turns"] <= 5)
            ensure(
                len(value["keywords"]) <= 30
                and all(isinstance(x, str) and 1 <= len(x) <= 80 for x in value["keywords"])
            )
            ensure(
                len(value["notify_roles"]) <= 20
                and all(isinstance(x, str) and len(x) <= 60 for x in value["notify_roles"])
            )
        if section == "knowledge_config":
            ensure(1 <= value["top_k"] <= 10 and 0 <= Decimal(value["min_score"]) <= 1)
        if section == "whatsapp_config":
            ensure(1 <= value["max_media_mb"] <= 50)
            if value["send_read_receipts"] or value["typing_indicator"]:
                raise BusinessRuleViolation(
                    "UNSUPPORTED_SETTING",
                    "Read receipts and typing indicators are not enabled by this deployment",
                )
    except (AssertionError, ValueError, TypeError, KeyError, InvalidOperation):
        raise BusinessRuleViolation("INVALID_SETTING", "Invalid PI configuration value") from None


def outside_hours(policy: PiSettings) -> bool:
    if not policy.business_hours.get("enabled"):
        return False
    now = datetime.now(UTC).astimezone(ZoneInfo(policy.timezone))
    key = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[now.weekday()]
    day = policy.business_hours["days"][key]
    return not day["open"] or not (
        time.fromisoformat(day["start"])
        <= now.time().replace(tzinfo=None)
        < time.fromisoformat(day["end"])
    )
