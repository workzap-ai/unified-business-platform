"""The full audit stamp of every pi reply (pi Brain spec 8.9, "Full audit").

"Every message is stamped with the versions, examples, arms and lessons it used; any reply can be
traced to why pi said it." `stamp` writes one `pi_reply_audits` row for one reply: the prompt
version, the version of each pack that fed the prompt, the lesson, example and wording ids that
`learning_context.build` stamped on the conversation for that turn, and the linter result. It
stores identifiers only, never text. It is safe to call for every reply, learning on or off
(a frozen workspace simply shows no learned ids), and calling it twice for one reply is harmless.

`send_whatsapp_message` calls `stamp_safely` once, after the reply message is saved (brain mode).
"""

import enum
import hashlib
import importlib
import json
import logging
import os
import re
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import industry_packs, learning, spec_handbook
from app.modules.pi.learning_models import PiReplyAudit
from app.modules.pi.models import PiAgentRun, PiConversation, PiMessage
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)


def _digest(path: Path) -> str:
    """A short hash of the file's raw bytes. This is the per-pack digest kept in audit rows and
    compared by the drift check (`drift_check._digest`, the industry rows), so it is left as it was
    on purpose; the combined `prompt_version` below normalises line endings instead."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except OSError:
        return ""


# The hardcoded prompt text and prompt-selection tables that reach a model: module -> names. A
# change to any of them changes pi's behaviour, so it changes `prompt_version`.
# `test_pi_prompt_version_coverage` scans every module of this package and fails when a prompt-like
# constant is neither listed here nor on its documented allowlist.
PROMPT_CONSTANTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "service_conversation",
        (
            "SYSTEM",
            "BRAIN_SYSTEM",
            "BRAIN_PROBLEMS",
            "BRAIN_DECISIONS",
            "BRAIN_VOICE",
            "BRAIN_ASK",
            "UNCONFIRMED_TRADE",
        ),
    ),
    ("think_prompt", ("PLAN_FIELD_HINT", "MOVE_LINES", "BLOCK", "MOVE_KEYS_TEXT")),
    ("think_plan", ("MOVE_KEYS_TEXT",)),
    (
        "expert_advisor",
        (
            "PERSONA",
            "STEER_RULES",
            "UNCONFIRMED_TRADE_RULE",
            "DIAGNOSE_RULES",
            "LIGHT_RULES",
            "JUDGE_RULES",
            "PROMPT_RULE",
            "VOICE_RULE",
        ),
    ),
    ("problem_extract", ("SYSTEM",)),
    ("solution_free", ("RULES",)),
    ("critique", ("SYSTEM",)),
    ("brain_docs", ("BOX_SYSTEM", "SYSTEM")),
    ("brain_prompt", ("CUTS",)),
    ("learning_voice", ("SYSTEM",)),
    ("learning_grader", ("SYSTEM", "RULE_BREAK_ITEMS", "QUALITY_ITEMS")),
    ("learning_miner", ("SYSTEM",)),
    ("learning_packs", ("SYSTEM",)),
    ("learning_solutions_grow", ("SYSTEM", "ENTRY_SYSTEM", "LESSONS")),
    ("ask_classifier", ("SYSTEM",)),
    ("graph", ("ROUTER_SYSTEM", "INTENTS", "AGENTS")),
    ("links", ("SUMMARY_SYSTEM",)),
    ("owner_intents", ("SYSTEM",)),
    (
        "owner_asks",
        (
            "NO_QUESTIONS_RULE",
            "RECALL_RULE",
            "SUGGEST_RULE",
            "NO_RECORDS_RULE",
            "PLAN_RULE",
            "REPEAT_RULE",
        ),
    ),
    ("memory_block", ("SYSTEM_LINE", "FACTS", "LABELS", "LABELS_UR", "FACT_KINDS")),
    ("runtime", ("IMAGE_INSTRUCTION",)),
    ("style", ("REPAIR",)),
    ("golden_replies", ("GOLDEN",)),
    ("flow", ("GUIDANCE", "NORMAL", "TRANSITIONS", "OPENING")),
    # Which handbook sections each state and topic selects, and how many examples: moving a section
    # between states changes the prompt without changing handbook.json.
    (
        "spec_handbook",
        (
            "CORE",
            "BY_STATE",
            "TOPICS",
            "GOLDEN_BY_STATE",
            "FRAME",
            "MAX_GOLDEN",
            "MAX_CHARS",
        ),
    ),
)

# Every pack file the prompt can draw on (industry, library, solutions, overlays, currency and the
# sector rules): the whole tree under `packs/`.
PACKS_ROOT = industry_packs.PACKS_DIR.parent


def _normal(data: bytes) -> bytes:
    """The same bytes whatever the checkout's line endings (a Windows checkout with CRLF and a
    Linux deploy with LF must give one version)."""
    return data.replace(b"\r\n", b"\n")


def _canon(value: Any) -> Any:
    """A constant as plain JSON data, in an order that cannot depend on how a dict or set was built.
    A pattern is its text and flags; an enum is its name. Anything else raises TypeError, so a
    default repr (with a memory address) can never enter the hash."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, bytes):
        return {"bytes": value.hex()}
    if isinstance(value, re.Pattern):
        return {"re": value.pattern, "flags": int(value.flags)}
    if isinstance(value, enum.Enum):
        return {"enum": type(value).__name__, "name": value.name}
    if isinstance(value, dict):
        pairs = [[json.dumps(_canon(k), sort_keys=True), _canon(v)] for k, v in value.items()]
        return {"dict": sorted(pairs, key=lambda pair: pair[0])}
    if isinstance(value, set | frozenset):
        return {"set": sorted(json.dumps(_canon(x), sort_keys=True) for x in value)}
    if isinstance(value, list | tuple):
        return [_canon(x) for x in value]
    raise TypeError(type(value).__name__)


def _text_of(value: Any) -> str:
    """A constant as text: a string as it is, anything else as canonical JSON."""
    if isinstance(value, str):
        return value
    return json.dumps(_canon(value), sort_keys=True, ensure_ascii=False)


@lru_cache(maxsize=1)
def _constants_digest() -> str:
    digest = hashlib.sha256()
    for module, names in PROMPT_CONSTANTS:
        try:
            target: Any = importlib.import_module(f"app.modules.pi.{module}")
        except Exception as exc:  # noqa: BLE001 - a missing module never costs a reply its audit
            logger.warning("pi_prompt_version_module_unreadable %s %s", module, type(exc).__name__)
            target = None
        for name in names:
            marker = ""
            body = ""
            if target is None:
                marker = "!module"
            elif not hasattr(target, name):
                marker = "!missing"
                logger.warning("pi_prompt_version_constant_missing %s.%s", module, name)
            else:
                try:
                    body = _text_of(getattr(target, name))
                except TypeError as exc:
                    marker = f"!unhashable:{exc}"
                    logger.warning(
                        "pi_prompt_version_constant_unhashable %s.%s %s", module, name, exc
                    )
            digest.update(f"{module}.{name}\n".encode())
            digest.update(marker.encode() if marker else _normal(body.encode("utf-8")))
            digest.update(b"\x00")
    return digest.hexdigest()


@lru_cache(maxsize=4)
def _packs_digest(root: str) -> str:
    """Relative path and (line-ending-normalised) bytes of every json file under the packs tree,
    in sorted path order: no absolute path, time or machine name enters it."""
    base = Path(root)
    digest = hashlib.sha256()
    for path in sorted(base.rglob("*.json"), key=lambda p: p.relative_to(base).as_posix()):
        try:
            data = path.read_bytes()
        except OSError:
            data = b"-"
        digest.update(path.relative_to(base).as_posix().encode("utf-8") + b"\x00")
        digest.update(_normal(data))
        digest.update(b"\x00")
    return digest.hexdigest()


def clear_prompt_cache() -> None:
    """Forget the hashes held for this process (a deploy starts a new process; tests call this)."""
    _constants_digest.cache_clear()
    _packs_digest.cache_clear()


def operator_guidance_digest(text: str | None) -> str:
    """A short hash of what the business wrote for pi in the Agents page, "" when it wrote none.
    Only the hash is ever kept, never the words (they can name people and numbers)."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    return hashlib.sha256(_normal(cleaned.encode("utf-8"))).hexdigest()[:12]


def prompt_version(operator_guidance: str | None = None) -> str:
    """Which prompt text was in force: a short hash of the specification handbook the model is
    given every turn, what the platform specification replaced in it, the hardcoded prompt
    constants, every pack file and, when given, the business's own operator guidance. It changes
    only when one of those changes. Without guidance (the workspace-independent version, what the
    reply stamp and the drift check compare) it stays the same for every workspace."""
    digest = hashlib.sha256()
    for path in (spec_handbook.PATH, spec_handbook.SUPERSESSION):
        try:
            digest.update(_normal(path.read_bytes()))
        except OSError:
            digest.update(b"-")
    digest.update(b"|prompts|" + _constants_digest().encode())
    digest.update(b"|packs|" + _packs_digest(str(PACKS_ROOT)).encode())
    if guidance := operator_guidance_digest(operator_guidance):
        digest.update(b"|guidance|" + guidance.encode())
    return digest.hexdigest()[:12]


def build_id() -> str:
    """Which code was running: the commit the host deployed (Railway sets one of these), else
    "unknown". Short, never a secret."""
    for name in ("RAILWAY_GIT_COMMIT_SHA", "GIT_COMMIT", "SOURCE_VERSION", "COMMIT_SHA"):
        if value := os.environ.get(name, "").strip():
            return value[:12]
    return "unknown"


def pack_versions(
    conversation: PiConversation,
    used: dict[str, Any],
    operator_guidance: str | None = None,
    *,
    guidance_unread: bool = False,
) -> dict[str, str]:
    """The packs behind this reply, by key, with a short hash of each file. The industry pack is the
    customer's industry when one was stamped; a learned pack is named by its id. The business's
    operator guidance is recorded as a hash under `operator_guidance` (never its words), and only
    when it wrote some, so a stored row without it keeps its old shape. `guidance_unread` marks a
    reply whose guidance could not be read, so a missing hash is not mistaken for "none written"."""
    out: dict[str, str] = {}
    if key := str(used.get("industry") or ""):
        path = industry_packs.PACKS_DIR / f"{key}.json"
        out[key] = _digest(path) or "unversioned"
    if learned := used.get("learned_pack"):
        out[f"learned:{learned}"] = "live"
    if guidance := operator_guidance_digest(operator_guidance):
        out["operator_guidance"] = guidance
    if guidance_unread:
        out["guidance_unread"] = "1"
    return out


def stamp_of(conversation: PiConversation, run: PiAgentRun | None) -> dict[str, Any]:
    """The `learning_used` stamp `learning_context.build` left for this reply's turn, or {}."""
    stamps = (conversation.service_brief or {}).get("learning_used") or []
    if run is None:
        return dict(stamps[-1]) if stamps else {}
    return next(
        (dict(x) for x in reversed(stamps) if x.get("message_id") == str(run.message_id)), {}
    )


async def operator_guidance_of(session: AsyncSession, scope: WorkspaceScope) -> str | None:
    """What this workspace wrote for pi in the Agents page (the current version of its requirement
    agent), "" when there is none and None when it could not be read. The same lookup the reply
    prompt uses."""
    from app.modules.pi.models import PiAgent, PiAgentVersion
    from app.shared.workspace_repository import WorkspaceRepository

    try:
        async with session.begin_nested():  # a failed read must not poison the reply's transaction
            version = await WorkspaceRepository(session, PiAgentVersion, scope).find(
                PiAgentVersion.agent_id.in_(
                    select(PiAgent.id).where(
                        WorkspaceRepository(session, PiAgent, scope).predicate(),
                        PiAgent.key == "requirement",
                        PiAgent.current_version == PiAgentVersion.version,
                    )
                )
            )
    except Exception:  # noqa: BLE001 - the audit is an extra, never a reason to lose it
        logger.warning("pi_reply_audit_guidance_unread", exc_info=True)
        return None
    return str(getattr(version, "instructions", "") or "")


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
    operator_guidance: str | None = None,
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
    guidance_unread = False
    if operator_guidance is None:
        read = await operator_guidance_of(session, scope)
        guidance_unread = read is None
        operator_guidance = read or ""
    row = PiReplyAudit(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        message_id=reply.id,
        conversation_id=conversation.id,
        run_id=run.id if run is not None else None,
        prompt_version=prompt or prompt_version(),
        pack_versions={
            **pack_versions(conversation, used, operator_guidance, guidance_unread=guidance_unread),
            "build": build_id(),
        },
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


async def stamp_safely(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    reply: PiMessage,
    **kwargs: Any,
) -> None:
    """`stamp` that can never fail the reply: the audit is an extra. It runs in a savepoint, so a
    database error rolls back only the stamp and the reply's own transaction stays healthy."""
    try:
        async with session.begin_nested():
            await stamp(session, scope, conversation, reply, **kwargs)
    except Exception:  # noqa: BLE001 - never a reason to lose a reply
        logger.warning("pi_reply_audit_failed", exc_info=True)


async def trace(
    session: AsyncSession, scope: WorkspaceScope, message_id: Any
) -> PiReplyAudit | None:
    """The audit row for a reply, for `/pi-trace` and the Brain screen. Only inside the workspace:
    another workspace's message id finds nothing."""
    found: PiReplyAudit | None = await session.scalar(
        select(PiReplyAudit).where(
            PiReplyAudit.tenant_id == scope.tenant_id,
            PiReplyAudit.environment_id == scope.environment_id,
            PiReplyAudit.message_id == message_id,
        )
    )
    return found
