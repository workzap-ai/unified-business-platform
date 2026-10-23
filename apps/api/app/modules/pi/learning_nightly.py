"""The nightly learning run (pi Brain spec 8.5), per workspace, with the morning digest (job 10).

For every workspace in brain mode and not more than once in 20 hours: if learning is frozen it
only writes a run row saying so and changes nothing (eval L10); otherwise it curates new example
candidates, activates the ripe ones, retires the poor and the surplus, and updates the question
arms from yesterday's outcomes. Every change is written to the change log. HIGH-risk things never
happen here: there is nothing in this run that touches money, privacy, the offer or the rules.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import (
    brain_config,
    experience_scorer,
    learning,
    learning_arms,
    learning_bank,
    learning_canary,
    learning_lexicon,
    learning_packs,
)
from app.modules.pi.learning_embed import Embedder
from app.modules.pi.learning_models import PiLearningRun
from app.modules.pi.models import PiSettings
from app.shared.scope import WorkspaceScope

MIN_GAP = timedelta(hours=20)
WriterFactory = Callable[[WorkspaceScope], learning_packs.Writer | None]


def scope_of(settings: PiSettings) -> WorkspaceScope:
    return WorkspaceScope.system(
        settings.tenant_id, settings.environment_id, frozenset(), "learning"
    )


async def last_run(session: AsyncSession, scope: WorkspaceScope) -> PiLearningRun | None:
    found: PiLearningRun | None = await session.scalar(
        select(PiLearningRun)
        .where(
            PiLearningRun.tenant_id == scope.tenant_id,
            PiLearningRun.environment_id == scope.environment_id,
        )
        .order_by(PiLearningRun.started_at.desc())
        .limit(1)
    )
    return found


async def run_workspace(
    session: AsyncSession,
    settings: PiSettings,
    now: datetime | None = None,
    embedder: Embedder | None = None,
    pack_writer: WriterFactory | None = None,
) -> PiLearningRun:
    """One run for one workspace. Returns the run row with its digest."""
    now = now or datetime.now(UTC)
    scope = scope_of(settings)
    previous = await last_run(session, scope)
    since = previous.started_at if previous is not None else now - timedelta(days=1)
    run = PiLearningRun(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        started_at=now,
        frozen=learning.frozen(settings.response_rules),
        digest={},
    )
    session.add(run)
    digest: dict[str, Any] = {}
    if run.frozen:
        digest["frozen"] = True  # the kill switch: no changes of any kind
    else:
        digest["examples"] = await learning_bank.curate(session, scope, now, embedder=embedder)
        rules = settings.response_rules
        digest["examples"].update(await learning_bank.activate(session, scope, now))
        digest["canary"] = await learning_canary.evaluate(
            session,
            scope,
            now,
            min_days=brain_config.value(rules, "canary_min_days"),
            min_uses=brain_config.value(rules, "canary_min_uses"),
        )
        digest["examples"]["retired_poor"] = await learning_bank.retire_poor(session, scope)
        digest["packs"] = await learning_packs.draft_new(
            session, scope, pack_writer(scope) if pack_writer else None, now
        )
        digest["packs"]["went_live"] = await learning_packs.promote_shadows(session, scope, now)
        digest["vocabulary"] = await learning_lexicon.learn(session, scope)
        digest["arms"] = await learning_arms.learn_from(session, scope, since)
        digest["health"] = await experience_scorer.health(session, now - timedelta(days=1), scope)
    run.digest = digest
    run.finished_at = datetime.now(UTC)
    await session.flush()
    return run


async def run_due(
    session: AsyncSession,
    now: datetime | None = None,
    embedder: Embedder | None = None,
    pack_writer: WriterFactory | None = None,
) -> int:
    """Run every brain-mode workspace that has not run in the last 20 hours. Returns how many."""
    now = now or datetime.now(UTC)
    rows = list(
        await session.scalars(
            select(PiSettings).where(PiSettings.response_rules["pi_mode"].astext == "brain")
        )
    )
    done = 0
    for settings in rows:
        previous = await last_run(session, scope_of(settings))
        if previous is not None and now - previous.started_at < MIN_GAP:
            continue
        await run_workspace(session, settings, now, embedder, pack_writer)
        done += 1
    return done
