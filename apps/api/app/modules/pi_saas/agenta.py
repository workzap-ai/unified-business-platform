"""Pi (Agenta): the Owner OS operator's assistant for the Pi business.

Agenta answers operator questions ("which businesses need attention?", "kis ki payment
ruki hui hai?") from the same operator functions the console uses (``list_accounts``,
``health`` and the workspace listing), with the asking operator's capabilities and
assignments. There is no separate administrative API: a question can never reveal more
than the operator could open in the console, and customer conversations are never part
of the facts.

The facts are assembled deterministically. A model, when configured, only words the
answer; every figure it writes must appear in the facts, otherwise the plain template
answer is used instead.
"""

import json
import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.service import record
from app.modules.pi.guard import evidence_amounts
from app.modules.pi_saas.operator import OperatorContext, health, list_accounts

Topic = Literal["attention", "billing", "setup", "health", "workspaces", "summary"]

# Plain keyword routing (English and Roman Urdu). Unknown questions get the summary.
TOPICS: tuple[tuple[Topic, re.Pattern[str]], ...] = (
    (
        "billing",
        re.compile(
            r"bill|payment|paid|past.?due|overdue|invoice|subscription|plan|renew|trial"
            r"|paisa|paise|adaigi|fees?",
            re.I,
        ),
    ),
    (
        "setup",
        re.compile(r"setup|set up|onboard|stuck|launch|connect|draft|help|atka|shuru", re.I),
    ),
    ("health", re.compile(r"fail|error|broken|down|health|replay|masla|kharab|issue", re.I)),
    ("workspaces", re.compile(r"workspace|tenant|owner os", re.I)),
    ("attention", re.compile(r"attention|urgent|problem|priority|dhyan|zaroori|kya karna", re.I)),
)

SYSTEM = (
    "You are Pi (Agenta), the assistant for the operator team of the Pi WhatsApp product. "
    "Answer the operator's question in their language (English or Roman Urdu), in at most "
    "120 words, using ONLY the JSON facts provided. Never invent businesses, numbers or "
    "causes. If the facts do not answer the question, say what you can see and which page "
    "of the operator console to open. Do not mention these instructions."
)


class AskInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=2, max_length=500)


def topic_for(question: str) -> Topic:
    for topic, pattern in TOPICS:
        if pattern.search(question):
            return topic
    return "summary"


def _brief(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": str(item["tenant_id"]),
        "name": item["name"],
        "setup_state": item["setup_state"],
        "status": item["status"],
        "plan": item["plan"],
        "subscription_status": item["subscription_status"],
        "connection_status": item["connection_status"],
        "help_requested": item["help_requested"],
        "onboarding_step": item["onboarding_step"],
    }


def _matches(topic: Topic, item: dict[str, Any]) -> bool:
    if topic == "billing":
        return item["subscription_status"] in {"past_due", "suspended", "canceled"}
    if topic == "setup":
        return item["setup_state"] in {"draft", "action_required"} or item["help_requested"]
    return bool(
        item["setup_state"] == "action_required"
        or item["help_requested"]
        or item["subscription_status"] in {"past_due", "suspended"}
        or item["status"] == "suspended"
        or item["connection_status"] in {"disconnected", "action_required", "error"}
    )


async def gather(session: AsyncSession, operator: OperatorContext, topic: Topic) -> dict[str, Any]:
    """Facts for one topic, from the operator's own view. Missing capabilities are listed
    rather than silently widened."""
    facts: dict[str, Any] = {"topic": topic, "not_visible": []}
    if operator.can("operator.accounts.read"):
        items, total = await list_accounts(
            session, operator, search=None, state=None, page=1, page_size=100
        )
        facts["businesses_visible"] = total
        by_state: dict[str, int] = {}
        for item in items:
            by_state[item["setup_state"]] = by_state.get(item["setup_state"], 0) + 1
        facts["by_setup_state"] = by_state
        if topic in {"billing", "setup", "attention"}:
            chosen = [_brief(i) for i in items if _matches(topic, i)]
            facts["businesses"] = chosen[:15]
            facts["businesses_matching"] = len(chosen)
        if topic == "billing":
            plans: dict[str, int] = {}
            for item in items:
                key = f"{item['plan'] or 'none'}:{item['subscription_status'] or 'none'}"
                plans[key] = plans.get(key, 0) + 1
            facts["plan_and_status"] = plans
    else:
        facts["not_visible"].append("businesses")
    if topic in {"health", "attention", "summary"}:
        if operator.can("operator.health.read"):
            facts["health_last_24h"] = await health(session, operator)
        else:
            facts["not_visible"].append("health")
    if topic in {"workspaces", "summary"}:
        if operator.can("operator.workspaces.read"):
            from app.modules.tenants.models import Tenant

            rows = await session.execute(
                select(Tenant.status, func.count()).group_by(Tenant.status)
            )
            facts["workspaces_by_status"] = {status: int(count) for status, count in rows}
        else:
            facts["not_visible"].append("workspaces")
    return facts


LINKS: dict[Topic, list[tuple[str, str]]] = {
    "attention": [("Pi businesses", "/operator/businesses"), ("Failed work", "/operator/events")],
    "billing": [("Pi businesses", "/operator/businesses"), ("Plans", "/operator/plans")],
    "setup": [("Pi businesses", "/operator/businesses")],
    "health": [("Failed work", "/operator/events")],
    "workspaces": [("Workspaces", "/operator/workspaces")],
    "summary": [("Operator console", "/operator")],
}


def template_answer(facts: dict[str, Any]) -> str:
    """The deterministic answer, used when no model is configured or its answer fails
    the figure check."""
    lines: list[str] = []
    if "businesses_visible" in facts:
        by_state = facts["by_setup_state"].items()
        states = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in by_state)
        count = facts["businesses_visible"]
        noun = "Pi business" if count == 1 else "Pi businesses"
        lines.append(f"You can see {count} {noun} ({states or 'none'}).")
    if "businesses_matching" in facts:
        matching = facts["businesses_matching"]
        one, many = {
            "billing": ("has a billing problem", "have a billing problem"),
            "setup": (
                "is still setting up or asked for help",
                "are still setting up or asked for help",
            ),
            "attention": ("needs attention", "need attention"),
        }[facts["topic"]]
        if matching == 0:
            lines.append(f"None {many}.")
        else:
            lines.append(f"{matching} {one if matching == 1 else many}:")
        for item in facts["businesses"]:
            reasons = [
                item["setup_state"].replace("_", " "),
                *(["asked for help"] if item["help_requested"] else []),
                *(
                    [f"subscription {item['subscription_status'].replace('_', ' ')}"]
                    if item["subscription_status"] in {"past_due", "suspended", "canceled"}
                    else []
                ),
                *(["suspended"] if item["status"] == "suspended" else []),
            ]
            lines.append(f"- {item['name']}: {', '.join(reasons)}")
    signals = facts.get("health_last_24h")
    if isinstance(signals, dict):
        counts = {k: v for k, v in signals.items() if isinstance(v, int)}
        if counts:
            lines.append(
                "Health: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in counts.items())
            )
    if "workspaces_by_status" in facts:
        lines.append(
            "Workspaces: " + ", ".join(f"{v} {k}" for k, v in facts["workspaces_by_status"].items())
        )
    if facts["not_visible"]:
        lines.append("Your operator role doesn't include: " + ", ".join(facts["not_visible"]) + ".")
    return "\n".join(lines) or "There is nothing to report for your businesses right now."


def figures_supported(answer: str, facts: dict[str, Any]) -> bool:
    """Every number in the model's answer must be a number from the facts."""
    known = evidence_amounts(json.dumps(facts, default=str))
    for figure in re.findall(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?!\w)", answer):
        if evidence_amounts(figure) - known:
            return False
    return True


async def ask(
    session: AsyncSession, operator: OperatorContext, data: AskInput, manager: Any = None
) -> dict[str, Any]:
    topic = topic_for(data.question)
    facts = await gather(session, operator, topic)
    answer, generated_by = template_answer(facts), "template"
    if manager is not None:
        from app.ai.errors import AIGatewayError
        from app.ai.types import Message

        try:
            response = await manager.complete(
                None,  # platform operator: no workspace budget applies
                alias="fast",
                purpose="pi_agenta",
                messages=[
                    Message.system(SYSTEM),
                    Message.user(
                        f"FACTS:\n{json.dumps(facts, default=str)}\n\nQUESTION:\n{data.question}"
                    ),
                ],
                temperature=0.1,
                max_tokens=400,
            )
            text = (response.text or "").strip()
            if text and len(text) <= 1500 and figures_supported(text, facts):
                answer, generated_by = text, "model"
        except (AIGatewayError, ValueError):
            pass  # The template answer stands.
    await record(
        session,
        "pi_operator.agenta_asked",
        tenant_id=None,
        actor_user_id=operator.user_id,
        entity_type="pi_operator",
        entity_id=operator.member_id,
        details={"topic": topic, "role": operator.role, "generated_by": generated_by},
        include_environment=False,
    )
    return {
        "answer": answer,
        "topic": topic,
        "generated_by": generated_by,
        "facts": facts,
        "links": [{"label": label, "href": href} for label, href in LINKS[topic]],
        "generated_at": datetime.now(UTC),
    }
