"""pi tests itself: a few scripted customer messages run through the Test-pi sandbox
(``playground.preview``: the same composer, knowledge search and reply guards as live
chats; nothing is sent and no conversation is saved). Each reply is judged by fixed,
deterministic rules (language, no prices, no "!", not filler-only, lists services...);
no second model judges it.

Results go to the audit log (``pi.health.self_test``, one row per scenario per run) and
Health shows the latest run. When a scenario fails for a reason pi can fix safely (a
services question found no knowledge: documents stuck or failed are read again), pi
fixes it and tests that scenario once more; anything else is shown with what to do.

AI usage is real and metered, so the set is small and the daily run is at most once a
day per business.
"""

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.audit.models import AuditEvent
from app.modules.audit.service import record
from app.modules.pi.knowledge import KnowledgeService
from app.modules.pi.language import detect_language
from app.modules.pi.models import KnowledgeDocument, WhatsAppConnection
from app.modules.pi.price_policy import NO_DISCLOSURE
from app.modules.pi.price_policy import check as price_check
from app.modules.pi.service_conversation import digit_fragments, mixed_line, says_nothing
from app.modules.pi_saas.playground import PlaygroundInput, Turn, preview
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)

ACTION = "pi.health.self_test"
DAILY_GAP = timedelta(hours=20)
LIST_LINE = re.compile(r"^\s*(?:[•\-*–]|\d{1,2}[.)])\s+\S", re.MULTILINE)
BOOKED = re.compile(r"\b(?:confirmed|booked|scheduled|is set|locked in)\b", re.IGNORECASE)
BRIEF = [
    ("customer", "I need a logo for my bakery, Crescent Bakers. Modern and simple."),
    (
        "pi",
        "Here is your brief:\n• Logo for Crescent Bakers\n• Modern, simple style\n"
        "Shall I send this to the team?",
    ),
]


@dataclass(frozen=True)
class Scenario:
    key: str
    title: str
    message: str
    history: tuple[tuple[str, str], ...] = ()
    lists: bool = False  # the answer lists services
    no_price: bool = False
    team: bool | None = None  # brief must (True) / must not (False) go to the team
    no_booking: bool = False


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("greeting", "Greets a new customer", "Hi"),
    Scenario("services", "Lists the services", "Tell me about your services", lists=True),
    Scenario(
        "services_roman_urdu",
        "Answers Roman Urdu in English",
        "aap kya kaam karte ho?",
        lists=True,
    ),
    Scenario("price", "Never invents a price", "How much does a logo cost?", no_price=True),
    Scenario(
        "brief_confirmed",
        "Sends the brief once the customer agrees",
        "Yes send it",
        tuple(BRIEF),
        team=True,
    ),
    Scenario(
        "brief_not_confirmed",
        "Holds the brief when the customer changes topic",
        "Do you also make websites?",
        tuple(BRIEF),
        team=False,
    ),
    Scenario(
        "meeting",
        "Takes a meeting time without promising it",
        "Tomorrow 10am",
        (
            ("customer", "Can we have a call to discuss my project?"),
            ("pi", "Happy to arrange a call. Which day and time suit you?"),
        ),
        no_booking=True,
    ),
)
BY_KEY = {s.key: s for s in SCENARIOS}
RESULTS: dict[bool | None, str] = {True: "ok", False: "failed", None: "skipped"}
OUTCOME: dict[str, bool | None] = {v: k for k, v in RESULTS.items()}
FIX_HINTS = {
    "services": "Add a Services page to Knowledge listing what you offer.",
    "services_roman_urdu": "Add a Services page to Knowledge listing what you offer.",
    "price": "Check the price rule in Settings → Response rules.",
    "greeting": "Review the greeting and tone in Settings → Response rules.",
}
FIX_HREFS = {
    "services": "/pi/knowledge",
    "services_roman_urdu": "/pi/knowledge",
    "price": "/pi/settings/response-rules",
    "greeting": "/pi/settings/response-rules",
}


def judge(scenario: Scenario, result: dict[str, Any]) -> tuple[bool | None, str]:
    """(passed, reason). ``None`` = not judged (AI unavailable right now)."""
    status = result.get("status")
    if status == "ai_unavailable":
        return None, "AI was unavailable, so this wasn't tested"
    reply = str(result.get("reply") or "").strip()
    if status == "blocked":
        return False, (
            f"pi's own checks held the reply back ({result.get('blocked_reason')}); "
            "a live customer would be handed to your team"
        )
    if not reply:
        return False, "pi gave no reply"
    if (other := mixed_line(reply, "en")) or detect_language(reply) == "roman_ur":
        return False, f"the reply wasn't all in English ({other or 'roman_ur'})"
    if "!" in reply:
        return False, "the reply used an exclamation mark"
    if says_nothing(reply):
        return False, "the reply only said something like 'feel free to ask'"
    if scenario.lists and len(LIST_LINE.findall(reply)) < 2 and reply.count(",") < 2:
        if not result.get("knowledge_used"):
            return False, "pi found nothing about your services in Knowledge"
        return False, "the reply didn't list the services"
    if scenario.no_price and result.get("price_rule") in NO_DISCLOSURE:
        found = price_check(reply, str(result["price_rule"])) or digit_fragments(reply)
        if found:
            shown = found if isinstance(found, str) else "; ".join(found)
            return False, f"the reply mentioned a price or number ({shown})"
    if scenario.team is True and not result.get("ready_for_team"):
        return False, "the customer agreed, but the brief wasn't sent to the team"
    if scenario.team is False and result.get("ready_for_team"):
        return False, "the brief was sent to the team although the customer didn't agree"
    if scenario.no_booking and BOOKED.search(reply):
        return False, "the reply promised the meeting before the team confirmed it"
    return True, "passed"


async def _one(
    session: AsyncSession,
    settings: Any,
    http: httpx.AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    scope: WorkspaceScope,
    scenario: Scenario,
) -> tuple[bool | None, str, dict[str, Any]]:
    data = PlaygroundInput(
        message=scenario.message,
        history=[Turn(role=role, text=text) for role, text in scenario.history],  # type: ignore[arg-type]
    )
    try:
        result = await preview(session, settings, http, sessions, scope, data)
    except Exception:  # noqa: BLE001 - a broken scenario is a failed one, never a crash
        logger.warning("pi_self_test_failed", extra={"scenario": scenario.key}, exc_info=True)
        await session.rollback()
        return False, "the test couldn't run (internal error)", {}
    passed, reason = judge(scenario, result)
    return passed, reason, result


async def _reread_documents(session: AsyncSession, scope: WorkspaceScope) -> int:
    """Read stuck or failed documents again (local re-split, no AI)."""
    knowledge = KnowledgeService(session, scope)
    rows = list(
        await session.scalars(
            WorkspaceRepository(session, KnowledgeDocument, scope)
            .select()
            .where(KnowledgeDocument.status.in_(["pending", "processing", "failed"]))
            .limit(20)
            .with_for_update()
        )
    )
    for row in rows:
        await knowledge.reindex(row, background=True)
    await session.commit()
    return len(rows)


def runner_scope(scope: WorkspaceScope) -> WorkspaceScope:
    """The sandbox needs pi.settings.manage; re-reading documents pi.knowledge.manage."""
    return WorkspaceScope.system(
        scope.tenant_id,
        scope.environment_id,
        frozenset(scope.permissions) | {"pi.read", "pi.settings.manage", "pi.knowledge.manage"},
        "pi Health",
    )


async def run_self_tests(
    session: AsyncSession,
    scope: WorkspaceScope,
    settings: Any,
    http: httpx.AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    *,
    record_scope: WorkspaceScope | None = None,
) -> list[dict[str, Any]]:
    """Run every scenario once (and a fixed one once more); record each result."""
    runner = runner_scope(scope)
    run_id = uuid4().hex[:12]
    results: list[dict[str, Any]] = []
    reread = False
    for scenario in SCENARIOS:
        passed, reason, result = await _one(session, settings, http, sessions, runner, scenario)
        retried = False
        if passed is False and scenario.lists and not result.get("knowledge_used") and not reread:
            reread = True
            fixed = await _reread_documents(session, runner)
            if fixed:
                from app.modules.pi_saas.health import FIXED_ACTION

                await record(
                    session,
                    FIXED_ACTION,
                    scope=record_scope or runner,
                    entity_type="pi_health",
                    details={
                        "check": "knowledge_stuck",
                        "what": f"Re-read {fixed} document(s) after a self-test found no knowledge",
                        "count": fixed,
                    },
                )
                await session.commit()
                retried = True
                passed, reason, result = await _one(
                    session, settings, http, sessions, runner, scenario
                )
        item = {
            "scenario": scenario.key,
            # "result", not "passed": the audit log redacts keys that look like passwords.
            "result": RESULTS[passed],
            "reason": reason,
            "reply": str(result.get("reply") or "")[:240],
            "retried": retried,
            "run": run_id,
        }
        await record(
            session,
            ACTION,
            scope=record_scope or runner,
            entity_type="pi_health",
            outcome="success" if passed else "failure",
            details=item,
        )
        await session.commit()
        results.append(item)
    return results


def _view(item: dict[str, Any], at: datetime) -> dict[str, Any]:
    key = str(item.get("scenario"))
    scenario = BY_KEY.get(key)
    passed = OUTCOME.get(str(item.get("result")))
    return {
        "key": key,
        "title": scenario.title if scenario else key,
        "message": scenario.message if scenario else "",
        "passed": passed,
        "reason": item.get("reason") or "",
        "reply": item.get("reply") or "",
        "retried": bool(item.get("retried")),
        "hint": FIX_HINTS.get(key, "") if passed is False else "",
        "href": FIX_HREFS.get(key) if passed is False else None,
        "at": at.isoformat(),
    }


def _day(column: Any) -> Any:
    return func.to_char(column, literal_column("'YYYY-MM-DD'"))


async def latest(session: AsyncSession, scope: WorkspaceScope) -> dict[str, Any]:
    """The latest result per scenario, the pass rate and 7 days of daily pass rates."""
    where = (
        (AuditEvent.tenant_id == scope.tenant_id)
        & (AuditEvent.environment_id == scope.environment_id)
        & (AuditEvent.action == ACTION)
        & (AuditEvent.created_at >= datetime.now(UTC) - timedelta(days=7))
    )
    rows = list(
        await session.scalars(
            select(AuditEvent).where(where).order_by(AuditEvent.created_at.desc()).limit(200)
        )
    )
    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str((row.details or {}).get("scenario"))
        if key in BY_KEY and key not in seen:
            seen[key] = _view(row.details or {}, row.created_at)
    scenarios = [seen[s.key] for s in SCENARIOS if s.key in seen]
    judged = [s for s in scenarios if s["passed"] is not None]
    passed = sum(1 for s in judged if s["passed"])
    today = datetime.now(UTC).date()
    days = {
        (today - timedelta(days=n)).isoformat(): {
            "day": (today - timedelta(days=n)).isoformat(),
            "passed": 0,
            "total": 0,
        }
        for n in range(6, -1, -1)
    }
    for row in rows:
        day = row.created_at.astimezone(UTC).date().isoformat()
        value = OUTCOME.get(str((row.details or {}).get("result")))
        if day in days and value is not None:
            days[day]["total"] += 1
            days[day]["passed"] += 1 if value else 0
    return {
        "last_run_at": rows[0].created_at.isoformat() if rows else None,
        "pass_rate": round(100 * passed / len(judged)) if judged else None,
        "passed": passed,
        "total": len(judged),
        "scenarios": scenarios,
        "daily": [
            {**d, "rate": round(100 * d["passed"] / d["total"]) if d["total"] else None}
            for d in days.values()
        ],
    }


async def due(session: AsyncSession, scope: WorkspaceScope) -> bool:
    """At most once a day, and only when there is knowledge to test against."""
    recent = await session.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.tenant_id == scope.tenant_id,
            AuditEvent.environment_id == scope.environment_id,
            AuditEvent.action == ACTION,
            AuditEvent.created_at >= datetime.now(UTC) - DAILY_GAP,
        )
    )
    if recent:
        return False
    ready = await session.scalar(
        select(func.count())
        .select_from(KnowledgeDocument)
        .where(
            WorkspaceRepository(session, KnowledgeDocument, scope).predicate(),
            KnowledgeDocument.status == "ready",
        )
    )
    return bool(ready)


async def self_test_daily(ctx: dict[str, Any]) -> int:
    """Cron job: test every business with an active WhatsApp number and knowledge, at
    most once a day each, in service mode only (where pi writes its own replies)."""
    from app.modules.pi.configuration import settings_row
    from app.modules.pi.runtime import system_scope
    from app.modules.pi.service_conversation import service_mode

    async with ctx["sessions"]() as session:
        connections = list(
            await session.scalars(
                select(WhatsAppConnection).where(WhatsAppConnection.status == "active")
            )
        )
    seen: set[tuple[Any, Any]] = set()
    tested = 0
    for connection in connections:
        key = (connection.tenant_id, connection.environment_id)
        if key in seen:
            continue
        seen.add(key)
        async with ctx["sessions"]() as session:
            try:
                scope = await system_scope(session, connection)
                if scope is None or not await due(session, scope):
                    continue
                policy = await settings_row(session, runner_scope(scope))
                if not await service_mode(session, scope, policy):
                    continue
                await session.commit()
                await run_self_tests(session, scope, ctx["settings"], ctx["http"], ctx["sessions"])
                tested += 1
            except Exception:  # noqa: BLE001 - one business never stops the others
                logger.warning("pi_self_test_daily_failed", exc_info=True)
    return tested
