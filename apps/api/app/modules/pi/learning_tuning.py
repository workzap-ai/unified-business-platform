"""Settings tuning (pi Brain spec 8.5 job 7, 9.10).

Timing settings move one step at a time, at most once a week per setting and one setting per run,
so a change can be told apart from the one before it. A step stays only if the reward did not fall
and no guardrail (rule breaks, opt-outs, complaints, confusion, corrections) rose against the week
before; otherwise it is undone and the next try goes the other way. Only timing settings are here:
nothing that belongs to a rule (one question, disclosure, the quote) and nothing that decides how
changes are judged (the canary numbers).
"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import brain_config, learning_rules
from app.modules.pi.experience_models import PiExperience
from app.modules.pi.learning_models import PiLearningChange
from app.modules.pi.models import PiSettings
from app.shared.scope import WorkspaceScope

TUNED = (
    "debounce_seconds",
    "followup_silence_hours",
    "paused_followup_days",
    "document_followup_first_days",
    "document_followup_second_days",
)
STEP = {  # how far one move goes, in the setting's own unit
    "debounce_seconds": 1,
    "followup_silence_hours": 2,
    "paused_followup_days": 1,
    "document_followup_first_days": 1,
    "document_followup_second_days": 1,
}
MIN_REPLIES = learning_rules.MIN_CANARY  # as many replies as a canary needs (spec 9.10 rule 3)
KINDS = ("setting_tuned", "setting_reverted")


async def _rates(
    session: AsyncSession, scope: WorkspaceScope, start: datetime, end: datetime
) -> learning_rules.Rates | None:
    rows = list(
        await session.scalars(
            select(PiExperience).where(
                PiExperience.tenant_id == scope.tenant_id,
                PiExperience.environment_id == scope.environment_id,
                PiExperience.scored_at >= start,
                PiExperience.scored_at < end,
            )
        )
    )
    if len(rows) < MIN_REPLIES:
        return None
    n = len(rows)

    def share(signal: str) -> float:
        return sum(1 for r in rows if signal in r.signals) / n

    return learning_rules.Rates(
        conversations=n,
        reward=sum(r.reward for r in rows) / n,
        rule_break=share("rule_break"),
        opt_out=share("opt_out"),
        complaint=share("complaint"),
        confusion=share("confusion"),
        correction=share("correction"),
    )


async def _latest(session: AsyncSession, scope: WorkspaceScope) -> dict[str, PiLearningChange]:
    """The most recent tuning change for each setting."""
    rows = await session.scalars(
        select(PiLearningChange)
        .where(
            PiLearningChange.tenant_id == scope.tenant_id,
            PiLearningChange.environment_id == scope.environment_id,
            PiLearningChange.kind.in_(KINDS),
        )
        .order_by(PiLearningChange.created_at.desc())
    )
    latest: dict[str, PiLearningChange] = {}
    for row in rows:
        latest.setdefault(str(row.after.get("key")), row)
    return latest


def _clamp(key: str, value: int) -> int:
    _, low, high = brain_config.TUNABLES[key]
    return max(low, min(high, value))


def _write(settings: PiSettings, key: str, value: int) -> None:
    rules = dict(settings.response_rules or {})
    brain = dict(rules.get("brain") or {})
    brain[key] = value
    rules["brain"] = brain
    settings.response_rules = rules


def _log(
    session: AsyncSession,
    scope: WorkspaceScope,
    kind: str,
    key: str,
    before: int,
    after: int,
    direction: int,
    reason: str,
    evidence: dict[str, Any],
) -> None:
    session.add(
        PiLearningChange(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            kind=kind,
            risk="medium",
            before={"key": key, "value": before, "direction": direction},
            after={"key": key, "value": after, "direction": direction},
            evidence=evidence,
            status="live",
            reason=reason,
        )
    )


async def tune(
    session: AsyncSession, scope: WorkspaceScope, settings: PiSettings, now: datetime
) -> dict[str, Any]:
    """At most one step this run. Returns what happened, for the digest."""
    latest = await _latest(session, scope)
    # One trial at a time, so its effect can be told apart: while a step is still inside its
    # week nothing else moves, and a trial that is ready to be judged goes before a new one.
    trials = {k: c for k, c in latest.items() if c.kind == "setting_tuned" and k in TUNED}
    if any(now - c.created_at < learning_rules.ONE_WEEK for c in trials.values()):
        return {"tuned": None, "waiting": True}
    due = [
        key
        for key in TUNED
        if key not in latest or now - latest[key].created_at >= learning_rules.ONE_WEEK
    ]
    due.sort(
        key=lambda k: (
            k not in trials,
            latest[k].created_at.timestamp() if k in latest else 0.0,
        )
    )
    for key in due:
        current = brain_config.value(settings.response_rules, key)
        last = latest.get(key)
        if last is not None and last.kind == "setting_tuned":
            before = int(last.before["value"])
            direction = int(last.after.get("direction", 1))
            control = await _rates(
                session, scope, last.created_at - timedelta(days=7), last.created_at
            )
            trial = await _rates(session, scope, last.created_at, now)
            if control is None or trial is None:
                return {"tuned": None, "waiting": True}  # too few replies to judge it yet
            evidence = {"control": control.__dict__, "trial": trial.__dict__}
            breached = learning_rules.breached(control, trial)
            if current != int(last.after["value"]):
                # Someone set it by hand since: that choice stands. The trial is closed.
                _log(
                    session,
                    scope,
                    "setting_reverted",
                    key,
                    current,
                    current,
                    -direction,
                    "set by hand; left alone",
                    evidence,
                )
                return {"tuned": None, "left_alone": key}
            if breached or trial.reward < control.reward:
                back = _clamp(key, before)
                _write(settings, key, back)
                reason = (
                    "guardrail rose: " + ", ".join(breached)
                    if breached
                    else "reward fell, so the step was undone"
                )
                _log(
                    session,
                    scope,
                    "setting_reverted",
                    key,
                    current,
                    back,
                    -direction,
                    reason,
                    evidence,
                )
                return {"reverted": key, "to": back, "why": reason}
        else:
            direction = int(last.after.get("direction", 1)) if last is not None else 1
            if await _rates(session, scope, now - timedelta(days=7), now) is None:
                continue  # no week of data yet to measure against
            evidence = {}
        step = STEP[key] if direction > 0 else -STEP[key]
        new = _clamp(key, current + step)
        if new == current:
            continue  # at the end of its tested range in this direction
        _write(settings, key, new)
        _log(
            session,
            scope,
            "setting_tuned",
            key,
            current,
            new,
            direction,
            "one step, tested for a week",
            evidence,
        )
        return {"tuned": key, "from": current, "to": new}
    return {"tuned": None}
