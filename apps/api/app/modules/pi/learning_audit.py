"""The full audit stamp of every pi reply (pi Brain spec 8.9, "Full audit").

"Every message is stamped with the versions, examples, arms and lessons it used; any reply can be
traced to why pi said it." `stamp` writes one `pi_reply_audits` row for one reply: the prompt
version, the version of each pack that fed the prompt, the lesson, example and wording ids that
`learning_context.build` stamped on the conversation for that turn, and the linter result. It
stores identifiers only, never text. It is safe to call for every reply, learning on or off
(a frozen workspace simply shows no learned ids), and calling it twice for one reply is harmless.

The runtime calls it once, after the reply message is saved (see the report: one line).
"""

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import industry_packs, learning, spec_handbook
from app.modules.pi.learning_models import PiReplyAudit
from app.modules.pi.models import PiAgentRun, PiConversation, PiMessage
from app.shared.scope import WorkspaceScope


def _digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except OSError:
        return ""


def prompt_version() -> str:
    """Which prompt text was in force: a short hash of the specification handbook the model is
    given every turn (it changes only when the spec is rebuilt)."""
    return _digest(spec_handbook.PATH)


def pack_versions(conversation: PiConversation, used: dict[str, Any]) -> dict[str, str]:
    """The packs behind this reply, by key, with a short hash of each file. The industry pack is the
    customer's industry when one was stamped; a learned pack is named by its id."""
    out: dict[str, str] = {}
    if key := str(used.get("industry") or ""):
        path = industry_packs.PACKS_DIR / f"{key}.json"
        out[key] = _digest(path) or "unversioned"
    if learned := used.get("learned_pack"):
        out[f"learned:{learned}"] = "live"
    return out


def stamp_of(conversation: PiConversation, run: PiAgentRun | None) -> dict[str, Any]:
    """The `learning_used` stamp `learning_context.build` left for this reply's turn, or {}."""
    stamps = (conversation.service_brief or {}).get("learning_used") or []
    if run is None:
        return dict(stamps[-1]) if stamps else {}
    return next(
        (dict(x) for x in reversed(stamps) if x.get("message_id") == str(run.message_id)), {}
    )


async def stamp(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    reply: PiMessage,
    *,
    violations: Sequence[Any] | None = None,
    response_rules: dict[str, Any] | None = None,
    run: PiAgentRun | None = None,
    prompt: str | None = None,
) -> PiReplyAudit:
    """Record why pi said this reply. `violations` are the linter's findings on the first draft
    (rule and message only are kept); an empty list means the draft passed."""
    existing: PiReplyAudit | None = await session.scalar(
        select(PiReplyAudit).where(
            PiReplyAudit.tenant_id == scope.tenant_id,
            PiReplyAudit.environment_id == scope.environment_id,
            PiReplyAudit.message_id == reply.id,
        )
    )
    if existing is not None:
        return existing
    if run is None:
        run = await session.scalar(
            select(PiAgentRun).where(PiAgentRun.response_message_id == reply.id)
        )
    used = stamp_of(conversation, run)
    found = list(violations or [])
    row = PiReplyAudit(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        message_id=reply.id,
        conversation_id=conversation.id,
        run_id=run.id if run is not None else None,
        prompt_version=prompt or prompt_version(),
        pack_versions=pack_versions(conversation, used),
        lesson_ids=[str(x) for x in used.get("lessons") or []],
        example_ids=[str(x) for x in used.get("examples") or []],
        arm_ids=[str(x) for x in (used.get("arm"), used.get("voice_arm")) if x],
        linter={
            "passed": not found,
            "violations": [
                {"rule": getattr(v, "rule", ""), "hard": bool(getattr(v, "hard", False))}
                for v in found[:10]
            ],
        },
        frozen=learning.frozen(response_rules),
    )
    session.add(row)
    await session.flush()
    return row


async def trace(session: AsyncSession, message_id: Any) -> PiReplyAudit | None:
    """The audit row for a reply, for `/pi-trace` and the Brain screen."""
    found: PiReplyAudit | None = await session.scalar(
        select(PiReplyAudit).where(PiReplyAudit.message_id == message_id)
    )
    return found
