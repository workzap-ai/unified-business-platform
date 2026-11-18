"""What nori says about a workspace, cleaned, and the text block the support model may rely on.

Every field is optional: nori sends null for what it does not have and pi never fills a gap. Text
fields are capped and stripped of control characters, because they are data placed below the rules
in the prompt and can never act as instructions.
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f‪-‮⁦-⁩]")
STATUSES = ("trial", "active", "expired", "suspended")
HEALTH = ("ok", "degraded", "incident")


def _text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    from app.modules.pi import safety

    # Free text from nori is data for the model: control characters out, personal data redacted.
    cleaned = " ".join(safety.redact_pii(_CONTROL.sub("", value)).text.split())[:limit]
    return cleaned or None


def _day(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        stamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC).date()


def _count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


@dataclass(frozen=True)
class Facts:
    name: str | None = None
    industry: str | None = None
    summary: str | None = None
    country: str | None = None
    plan: str | None = None
    status: str | None = None
    trial_ends: date | None = None
    subscription_ends: date | None = None
    credits: int | None = None
    credits_low: bool | None = None
    health: str | None = None
    health_note: str | None = None

    def days_left(self, today: date) -> int | None:
        """Days until the trial (when on trial) or the subscription ends; negative once past."""
        end = self.trial_ends if self.status == "trial" else self.subscription_ends
        return None if end is None else (end - today).days

    def block(self, today: date) -> str:
        """The facts as plain lines. Only what nori sent; a missing field is simply absent."""
        lines: list[str] = []

        def add(label: str, value: object) -> None:
            if value not in (None, ""):
                lines.append(f"{label}: {value}")

        add("Workspace name", self.name)
        add("Business", self.industry)
        add("About the business", self.summary)
        add("Country", self.country)
        add("Plan", self.plan)
        add("Status", self.status)
        if self.trial_ends:
            add("Trial ends on", f"{self.trial_ends.day} {self.trial_ends:%B %Y}")
        if self.subscription_ends:
            add(
                "Subscription ends on",
                f"{self.subscription_ends.day} {self.subscription_ends:%B %Y}",
            )
        left = self.days_left(today)
        if left is not None:
            add("Days left" if left >= 0 else "Days since it ended", abs(left))
        if self.credits is not None:
            add("Credits left", self.credits)
        if self.credits_low is not None:
            add("Credits are low", "yes" if self.credits_low else "no")
        add("Nori health", self.health)
        add("Health note", self.health_note)
        return "\n".join(lines)


def parse(workspace: dict[str, Any] | None) -> Facts | None:
    """Facts from nori's `workspace` object, or None when there is nothing usable."""
    if not isinstance(workspace, dict):
        return None
    business = _obj(workspace.get("business"))
    health = _obj(workspace.get("health"))
    status = _text(workspace.get("status"), 20)
    state = _text(health.get("status"), 20)
    facts = Facts(
        name=_text(workspace.get("name"), 120),
        industry=_text(business.get("industry"), 120),
        summary=_text(business.get("summary"), 400),
        country=_text(business.get("country"), 60),
        plan=_text(workspace.get("plan"), 60),
        status=status.lower() if status and status.lower() in STATUSES else None,
        trial_ends=_day(workspace.get("trial_ends_at")),
        subscription_ends=_day(workspace.get("subscription_ends_at")),
        credits=_count(workspace.get("credits")),
        credits_low=workspace.get("credits_low")
        if isinstance(workspace.get("credits_low"), bool)
        else None,
        health=state.lower() if state and state.lower() in HEALTH else None,
        health_note=_text(health.get("note"), 300),
    )
    return facts if facts.block(date.today()) else None
