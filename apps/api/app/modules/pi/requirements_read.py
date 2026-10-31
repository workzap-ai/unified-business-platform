"""L2-1: read the owner's structured requirements back (the missing read of B2a).

`read_requirements` returns, for one customer (or for the customer of one conversation), the
constraints, the things tried, the cause and the expected outcome of the customer's active
problems, as plain dataclasses (`requirements_types`). Read-only, scoped by tenant AND environment.

The four columns are deferred on `PiProblem` so that code deployed before migration 0053 keeps
working. This reader never relies on a lazy load (an async session cannot do one): it selects the
columns explicitly, as columns and not as ORM objects, so nothing deferred is ever left to load
and no stale identity-map value can be returned. On a database without the 0053 columns the
select fails with "undefined column" (SQLSTATE 42703); that one error, inside a savepoint so the
caller's transaction stays usable, becomes empty requirements with `columns_available=False`.
Every other error propagates.

Logs carry counts only, never the owner's words.
"""

import logging
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import taxonomy
from app.modules.pi.models import PiConversation
from app.modules.pi.problem_models import PiProblem
from app.modules.pi.requirements_types import (
    Cause,
    Constraints,
    Limit,
    ProblemRequirements,
    Requirements,
    TriedItem,
)
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)

UNDEFINED_COLUMN = "42703"


def _text(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _limit(value: Any) -> Limit | None:
    if not isinstance(value, Mapping):
        return None
    text = _text(value.get("text"))
    msg = value.get("msg")
    return Limit(text, msg if isinstance(msg, str) and msg else None) if text else None


def parse_constraints(raw: Any) -> Constraints:
    if not isinstance(raw, Mapping):
        return Constraints()
    listed = raw.get("cannot_change")
    items = tuple(x for x in map(_limit, listed if isinstance(listed, list) else []) if x)
    return Constraints(
        budget=_limit(raw.get("budget")),
        staff=_limit(raw.get("staff")),
        deadline=_limit(raw.get("deadline")),
        cannot_change=items,
    )


def parse_tried(raw: Any) -> tuple[TriedItem, ...]:
    out: list[TriedItem] = []
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, Mapping):
            continue
        what = _text(entry.get("what"))
        if what:
            msg = entry.get("msg")
            out.append(
                TriedItem(what, _text(entry.get("outcome")), msg if isinstance(msg, str) else None)
            )
    return tuple(out)


def parse_cause(raw: Any) -> Cause | None:
    if not isinstance(raw, Mapping):
        return None
    text = _text(raw.get("text"))
    if not text:
        return None
    status = raw.get("status")
    evidence = raw.get("evidence")
    evidence = evidence if isinstance(evidence, Mapping) else {}
    words = evidence.get("words")
    msgs = evidence.get("msgs")
    return Cause(
        text=text,
        status=status if isinstance(status, str) and status else "pi_inferred",
        evidence_words=tuple(_text(w) for w in words if _text(w))
        if isinstance(words, list)
        else (),
        evidence_msgs=tuple(m for m in msgs if isinstance(m, str))
        if isinstance(msgs, list)
        else (),
    )


def parse_row(row: Any) -> ProblemRequirements:
    """One selected row as requirements. Anything malformed in a column reads as "not said"."""
    return ProblemRequirements(
        problem_id=row.id,
        number=int(row.number or 0),
        title=_text(row.title),
        constraints=parse_constraints(row.constraints),
        tried=parse_tried(row.tried),
        cause=parse_cause(row.cause),
        expected_outcome=_text(row.expected_outcome),
    )


def _undefined_column(error: ProgrammingError) -> bool:
    orig = error.orig
    for candidate in (orig, getattr(orig, "__cause__", None)):
        if candidate is None:
            continue
        if getattr(candidate, "sqlstate", None) == UNDEFINED_COLUMN:
            return True
        if getattr(candidate, "pgcode", None) == UNDEFINED_COLUMN:
            return True
        if type(candidate).__name__ == "UndefinedColumnError":
            return True
    return False


async def _customer_of(
    session: AsyncSession, scope: WorkspaceScope, conversation_id: UUID
) -> UUID | None:
    found: UUID | None = await session.scalar(
        select(PiConversation.customer_id).where(
            PiConversation.tenant_id == scope.tenant_id,
            PiConversation.environment_id == scope.environment_id,
            PiConversation.id == conversation_id,
        )
    )
    return found


async def read_requirements(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    customer_id: UUID | None = None,
    conversation_id: UUID | None = None,
) -> Requirements:
    """The requirements of the customer's active problems, oldest problem first.

    Give a customer id, a conversation id (its customer is looked up inside the same tenant and
    environment) or both (they must agree, else nothing is returned). Requirements belong to the
    customer, so a new chat of the same customer sees what an earlier one noted.
    """
    if customer_id is None and conversation_id is None:
        raise ValueError("read_requirements needs a customer_id or a conversation_id")
    if conversation_id is not None:
        owner = await _customer_of(session, scope, conversation_id)
        if owner is None or (customer_id is not None and owner != customer_id):
            return Requirements()
        customer_id = owner
    query = (
        select(
            PiProblem.id,
            PiProblem.number,
            PiProblem.title,
            PiProblem.constraints,
            PiProblem.tried,
            PiProblem.cause,
            PiProblem.expected_outcome,
        )
        .where(
            PiProblem.tenant_id == scope.tenant_id,
            PiProblem.environment_id == scope.environment_id,
            PiProblem.customer_id == customer_id,
            PiProblem.status.in_(taxonomy.ACTIVE),
        )
        .order_by(PiProblem.number)
    )
    try:
        async with session.begin_nested():
            rows = (await session.execute(query)).all()
    except ProgrammingError as error:
        if not _undefined_column(error):
            raise
        logger.warning("pi_requirements_columns_missing")
        return Requirements(columns_available=False)
    problems = tuple(parse_row(row) for row in rows)
    logger.info(
        "pi_requirements_read",
        extra={"problems": len(problems), "with_requirements": sum(not p.empty for p in problems)},
    )
    return Requirements(problems=problems)
