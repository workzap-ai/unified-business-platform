"""The full audit stamp of every pi reply (pi Brain spec 8.9, "Full audit").

"Every message is stamped with the versions, examples, arms and lessons it used; any reply can be
traced to why pi said it." `stamp` writes one `pi_reply_audits` row for one reply: the prompt
version, the version of each pack that fed the prompt, the lesson, example and wording ids that
`learning_context.build` stamped on the conversation for that turn, and the linter result. It
stores identifiers only, never text. It is safe to call for every reply, learning on or off
(a frozen workspace simply shows no learned ids), and calling it twice for one reply is harmless.

`send_whatsapp_message` calls `stamp_safely` once, after the reply message is saved (brain mode).

`prompt_version` hashes the SOURCE FILES of every prompt-bearing module, not a list of constants (a
list can never be complete: prompts are also inline literals, f-strings and selection logic). The
set is every `.py` file under `app/modules/pi` (except `evalkit/`) that is not named on
`NON_PROMPT_MODULES` with a reason, plus `EXTERNAL_PROMPT_MODULES`; a new module is hashed by
default, and it can leave the hash only by being named there. The pack files, the handbook JSON and
the optional operator guidance are hashed as before.

Consequence, intended and tolerated: ANY edit to a hashed module's source, a comment included,
changes `prompt_version`, so the first replies after a deploy carry a new version and the drift
check reports `stale_prompt` once (`drift_check.stamp_findings`, `drift_check.stamp_summary`)
until the new version is the one stamped. Not covered: behaviour driven by data outside these files
(database settings, learned lessons and examples; the operator guidance only through its own
optional hash).
See docs/pi-saas/pi-prompt-version.md.
"""

import hashlib
import importlib.util
import logging
import os
from collections.abc import Callable, Sequence
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


# Where the prompt-bearing source lives: every .py file under this folder is hashed unless it is
# named on NON_PROMPT_MODULES below (a new module is therefore hashed by default).
PI_ROOT = Path(__file__).resolve().parent
# The evaluation kit and bytecode are not shipped prompts.
EXCLUDED_DIRS = ("evalkit", "__pycache__")

# Source outside this folder that reaches the model (runtime.py imports IMAGE_INSTRUCTION from
# there).
EXTERNAL_PROMPT_MODULES: tuple[str, ...] = ("app.ai.media",)

_R_MODELS = "SQLAlchemy table definitions: the shape of stored data, no text sent to a model"
_R_ROUTES = "HTTP handlers and request bodies: no model message is built here"

# Modules that leave the hash, each named with a reason. `test_pi_prompt_version_coverage` fails
# on a stale entry and when an entry builds a model message or calls the model.
NON_PROMPT_MODULES: dict[str, str] = {
    **dict.fromkeys(
        (
            "box_models.py brain_docs_models.py business_models.py business_profile_models.py "
            "experience_models.py learning_models.py models.py open_item_models.py "
            "problem_models.py quarantine_models.py solution_models.py think_models.py"
        ).split(),
        _R_MODELS,
    ),
    **dict.fromkeys(
        (
            "brain_doc_routes.py brain_erase_routes.py brain_health_routes.py "
            "brain_learning_routes.py brain_moderation_routes.py brain_visual_routes.py "
            "business_profile_routes.py config_routes.py inbox_routes.py kapso_routes.py "
            "open_items_routes.py read_routes.py routes.py solution_routes.py "
            "staff_review_routes.py"
        ).split(),
        _R_ROUTES,
    ),
    "schemas.py": "API request and response schemas: not sent to a model",
    "__init__.py": "package marker",
    "tools/__init__.py": "package marker",
    "learning_audit.py": "this version machinery; it holds no prompt text",
    "drift_check.py": "the drift report: it reads the version and the prompt files, sends nothing",
    "latency.py": "per-turn timing log: no prompt text",
}

# Every pack file the prompt can draw on (industry, library, solutions, overlays, currency and the
# sector rules): the whole tree under `packs/`.
PACKS_ROOT = industry_packs.PACKS_DIR.parent

# A digest is kept for the life of the process only when every file it needs could be read; a
# failure is never cached, so the next call retries. A file that cannot be read is logged once.
_CACHE: dict[tuple[str, str], str] = {}
_WARNED: set[str] = set()


def _normal(data: bytes) -> bytes:
    """The same bytes whatever the checkout's line endings (a Windows checkout with CRLF and a
    Linux deploy with LF must give one version)."""
    return data.replace(b"\r\n", b"\n")


def _read(path: Path, label: str) -> bytes | None:
    """The file's bytes, or None after one warning per label (never the path, never the content)."""
    try:
        return path.read_bytes()
    except OSError as exc:
        if label not in _WARNED:
            _WARNED.add(label)
            logger.warning("pi_prompt_version_unreadable %s %s", label, type(exc).__name__)
        return None


def _hash_files(items: Sequence[tuple[str, Path]]) -> tuple[str, bool]:
    """Label and normalised bytes of each file in sorted label order: no absolute path, time or
    machine name enters it. The flag is False when any file was unreadable (marked, not cached)."""
    digest = hashlib.sha256()
    complete = True
    for label, path in sorted(items, key=lambda item: item[0]):
        data = _read(path, label)
        if data is None:
            complete = False
            data = b"-"
        digest.update(label.encode("utf-8") + b"\x00")
        digest.update(_normal(data))
        digest.update(b"\x00")
    return digest.hexdigest(), complete


def _cached(kind: str, root: str, build: Callable[[], tuple[str, bool]]) -> str:
    key = (kind, root)
    if key in _CACHE:
        return _CACHE[key]
    value, complete = build()
    if complete:
        _CACHE[key] = value
    return value


def all_module_files(root: Path | None = None) -> dict[str, Path]:
    """Every .py file under the pi folder (evalkit and bytecode folders excluded), by its path
    relative to the folder, e.g. `service_conversation.py`, `tools/handlers.py`."""
    base = PI_ROOT if root is None else root
    found: dict[str, Path] = {}
    for path in base.rglob("*.py"):
        label = path.relative_to(base).as_posix()
        if label.split("/")[0] in EXCLUDED_DIRS or "__pycache__" in label:
            continue
        found[label] = path
    return found


def prompt_source_files(root: Path | None = None) -> dict[str, Path]:
    """The source files that make up the version: every module except those named on
    NON_PROMPT_MODULES, and the external prompt modules (found without importing them)."""
    files = {k: v for k, v in all_module_files(root).items() if k not in NON_PROMPT_MODULES}
    for name in EXTERNAL_PROMPT_MODULES:
        label = f"ext/{name}"
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError):
            spec = None
        files[label] = Path(spec.origin) if spec is not None and spec.origin else Path(name)
    return files


def _sources_digest(root: str) -> str:
    return _cached(
        "sources", root, lambda: _hash_files(list(prompt_source_files(Path(root)).items()))
    )


def _packs_digest(root: str) -> str:
    def build() -> tuple[str, bool]:
        base = Path(root)
        items = [(p.relative_to(base).as_posix(), p) for p in base.rglob("*.json")]
        return _hash_files(items)

    return _cached("packs", root, build)


def clear_prompt_cache() -> None:
    """Forget the hashes held for this process (a deploy starts a new process; tests call this)."""
    _CACHE.clear()
    _WARNED.clear()


def operator_guidance_digest(text: str | None) -> str:
    """A short hash of what the business wrote for pi in the Agents page, "" when it wrote none.
    Only the hash is ever kept, never the words (they can name people and numbers)."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    return hashlib.sha256(_normal(cleaned.encode("utf-8"))).hexdigest()[:12]


def prompt_version(operator_guidance: str | None = None) -> str:
    """Which prompt text was in force: a short hash of the specification handbook the model is
    given every turn, what the platform specification replaced in it, the source of every
    prompt-bearing module, every pack file and, when given, the business's own operator guidance.
    It changes only when one of those changes (an edit to a hashed module's source, a comment
    included, counts). Without guidance (the workspace-independent version, what the reply stamp and
    the drift check compare) it stays the same for every workspace."""
    digest = hashlib.sha256()
    for path in (spec_handbook.PATH, spec_handbook.SUPERSESSION):
        data = _read(path, f"spec/{path.name}")
        digest.update(_normal(data) if data is not None else b"-")
    digest.update(b"|sources|" + _sources_digest(str(PI_ROOT)).encode())
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
