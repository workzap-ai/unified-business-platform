import re
from datetime import UTC, datetime, time, tzinfo
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.modules.pi.brain_config import TUNABLES
from app.modules.pi.models import PiSettings
from app.modules.pi.price_policy import PRICE_MODES
from app.modules.pi.safety import REGULATED_TRADES
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
            ensure(
                bool(
                    re.fullmatch(
                        r"auto|roman_ur|[a-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})?", value["language"]
                    )
                )
            )
            ensure(value["service_mode"] in {"auto", "service"})
            ensure(value.get("pi_mode", "standard") in {"standard", "brain"})
            brain = value.get("brain", {})  # tunables and the learning switch (spec 9.9)
            flags = {
                "learning_frozen",
                "served_industries",
                "critique",
                "solution_mode",
                "map_share",
                "box_offer",
                "thinking",
                "drift_check",
                "solution_source",
                "expert_judge",
                "warmup",
                "idea_link",
                "fact_ask",
                "list_guard",
            }
            ensure(isinstance(brain, dict) and set(brain) <= {*TUNABLES, *flags})
            ensure(type(brain.get("learning_frozen", True)) is bool)
            ensure(type(brain.get("critique", False)) is bool)
            ensure(type(brain.get("solution_mode", False)) is bool)  # Addendum 2 value line
            ensure(type(brain.get("map_share", False)) is bool)  # Book 5 4.4: share the map
            ensure(type(brain.get("box_offer", False)) is bool)  # Book 5 5.4: the box offer rule
            ensure(type(brain.get("thinking", False)) is bool)  # Book 5 Part 3: dials and moves
            ensure(type(brain.get("drift_check", False)) is bool)  # Part A.7: daily drift run
            ensure(brain.get("solution_source", "packs_first") in {"packs_first", "expert"})
            ensure(type(brain.get("expert_judge", True)) is bool)  # skip the judge call when false
            ensure(type(brain.get("warmup", False)) is bool)  # spec v1.4 Part 16: the opening
            ensure(type(brain.get("idea_link", False)) is bool)  # v1.5 18.4 G12, opt-in
            ensure(type(brain.get("fact_ask", False)) is bool)  # v1.5 18.5 alreadyAnswered, opt-in
            ensure(type(brain.get("list_guard", False)) is bool)  # B1: no list item dropped, opt-in
            ensure(all(type(v) is int for k, v in brain.items() if k not in flags))
            served = brain.get("served_industries", [])  # regulated trades Workzap serves (7.N)
            ensure(isinstance(served, list) and set(served) <= set(REGULATED_TRADES))
            ensure(value.get("price_disclosure", "") in ("", *PRICE_MODES))
            ensure(value.get("execution_mode", "") in ("", "human_approved", "mixed", "ai_led"))
            ensure(
                bool(re.fullmatch(r"[a-z]{2,3}", str(value.get("staff_summary_language", "en"))))
            )
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
            departments = value.get("departments", [])
            ensure(1 <= len(departments) <= 20)
            keys = []
            for item in departments:
                ensure(isinstance(item, dict) and set(item) == {"key", "name", "description"})
                ensure(bool(re.fullmatch(r"[a-z0-9_]{2,40}", str(item["key"]))))
                ensure(isinstance(item["name"], str) and 1 <= len(item["name"].strip()) <= 60)
                ensure(isinstance(item["description"], str) and len(item["description"]) <= 300)
                keys.append(item["key"])
            ensure(len(set(keys)) == len(keys))
            examples = value.get("department_examples", [])
            ensure(len(examples) <= 40)
            for item in examples:
                ensure(isinstance(item, dict) and set(item) == {"text", "department"})
                ensure(isinstance(item["text"], str) and 1 <= len(item["text"]) <= 400)
                ensure(item["department"] in keys)
        if section == "knowledge_config":
            ensure(1 <= value["top_k"] <= 10 and 0 <= Decimal(value["min_score"]) <= 1)
        if section == "whatsapp_config":
            ensure(1 <= value["max_media_mb"] <= 50)
            ensure(1 <= value["reminder_after_days"] <= 30)
            ensure(isinstance(value.get("check_in_enabled", True), bool))
            ensure(1 <= int(value.get("check_in_after_hours", 2)) <= 12)
            ensure(isinstance(value.get("business_form", True), bool))
            ensure(0 <= int(value.get("quiet_start", 21)) <= 23)
            ensure(0 <= int(value.get("quiet_end", 9)) <= 23)
            from app.modules.pi_saas.flows import valid_config

            ensure(valid_config(value.get("flows", {})))
            templates = value["reminder_templates"]
            ensure(len(templates) <= 50)
            for language, template in templates.items():
                ensure(
                    bool(re.fullmatch(r"roman_ur|[a-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})?", language))
                )
                ensure(isinstance(template, dict) and set(template) == {"name", "language"})
                ensure(bool(re.fullmatch(r"[a-z0-9_]{1,512}", template["name"])))
                ensure(bool(re.fullmatch(r"[a-z]{2,3}(?:_[A-Z]{2})?", template["language"])))
            code = value.get("code_template", {})
            ensure(isinstance(code, dict) and set(code) <= {"name", "language"})
            if code:
                ensure(bool(re.fullmatch(r"[a-z0-9_]{1,512}", str(code.get("name", "")))))
                ensure(
                    bool(re.fullmatch(r"[a-z]{2,3}(?:_[A-Z]{2})?", str(code.get("language", ""))))
                )
            meeting = value.get("meeting_templates", {})
            ensure(isinstance(meeting, dict) and len(meeting) <= 50)
            for language, template in meeting.items():
                ensure(
                    bool(re.fullmatch(r"roman_ur|[a-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})?", language))
                )
                ensure(isinstance(template, dict) and {"name", "language"} <= set(template))
                ensure(set(template) <= {"name", "language", "status"})
                ensure(bool(re.fullmatch(r"[a-z0-9_]{1,512}", template["name"])))
                ensure(bool(re.fullmatch(r"[a-z]{2,3}(?:_[A-Z]{2})?", template["language"])))
                ensure(isinstance(template.get("status", ""), str))
            followups = value.get("followup_templates", {})
            ensure(isinstance(followups, dict) and len(followups) <= 50)
            for language, kinds in followups.items():
                ensure(
                    bool(re.fullmatch(r"roman_ur|[a-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})?", language))
                )
                ensure(isinstance(kinds, dict) and set(kinds) <= {"paused", "documents"})
                for template in kinds.values():
                    ensure(isinstance(template, dict) and set(template) == {"name", "language"})
                    ensure(bool(re.fullmatch(r"[a-z0-9_]{1,512}", template["name"])))
                    ensure(bool(re.fullmatch(r"[a-z]{2,3}(?:_[A-Z]{2})?", template["language"])))
            ladder = value.get("ladder_templates", {})
            ensure(isinstance(ladder, dict) and len(ladder) <= 50)
            for language, steps in ladder.items():
                ensure(
                    bool(re.fullmatch(r"roman_ur|[a-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})?", language))
                )
                ensure(isinstance(steps, dict) and set(steps) <= {"day3", "day7", "day14"})
                for template in steps.values():
                    ensure(isinstance(template, dict) and set(template) == {"name", "language"})
                    ensure(bool(re.fullmatch(r"[a-z0-9_]{1,512}", template["name"])))
                    ensure(bool(re.fullmatch(r"[a-z]{2,3}(?:_[A-Z]{2})?", template["language"])))
            if value["send_read_receipts"] or value["typing_indicator"]:
                raise BusinessRuleViolation(
                    "UNSUPPORTED_SETTING",
                    "Read receipts and typing indicators are not enabled by this deployment",
                )
    except (AssertionError, ValueError, TypeError, KeyError, InvalidOperation):
        raise BusinessRuleViolation("INVALID_SETTING", "Invalid PI configuration value") from None


def zone(name: str) -> tzinfo:
    """IANA zone; UTC works even where the OS has no tz database (Windows without
    the tzdata package). Other names still need a tz database and fail loudly."""
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        if name in {"UTC", "Etc/UTC", "GMT"}:
            return UTC
        raise


def outside_hours(policy: PiSettings) -> bool:
    if not policy.business_hours.get("enabled"):
        return False
    now = datetime.now(UTC).astimezone(zone(policy.timezone))
    key = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[now.weekday()]
    day = policy.business_hours["days"][key]
    return not day["open"] or not (
        time.fromisoformat(day["start"])
        <= now.time().replace(tzinfo=None)
        < time.fromisoformat(day["end"])
    )
