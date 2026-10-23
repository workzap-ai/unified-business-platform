"""What the learning brain adds to one turn's context (pi Brain spec 8.4.3, 8.4.5).

Only when the workspace has switched learning on: `response_rules.pi_mode` is "brain" and
`response_rules.brain.learning_frozen` is exactly False. Then pi may see up to three redacted
examples of replies that worked in a similar situation and one suggested wording for the next
question. Both are reference material the prompt places below the rules. Which ones were shown is
stamped on the conversation so the outcome can be credited to them afterwards.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import (
    learning,
    learning_arms,
    learning_bank,
    learning_lessons,
    learning_packs,
    learning_voice,
    solution_context,
)
from app.modules.pi.language import detect_language
from app.modules.pi.learning_embed import Embedder
from app.modules.pi.models import PiConversation, PiMessage
from app.shared.scope import WorkspaceScope

STAMPS_KEPT = 8


def active(response_rules: dict[str, Any] | None) -> bool:
    rules = response_rules or {}
    return rules.get("pi_mode") == "brain" and not learning.frozen(rules)


async def build(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    message: PiMessage | None,
    noted: list[dict[str, Any]],
    embedder: Embedder | None = None,
    canary_percent: int = 10,
    solution_mode: bool = False,
) -> dict[str, Any]:
    """`learned_examples`, `question_hint` and `lessons` for this turn (each may be missing)."""
    said = message.body if message is not None and message.body else ""
    language = detect_language(said) or conversation.language or "en"
    language = language if language in ("en", "roman_ur", "ar") else "en"
    state = conversation.flow_state or ""
    out: dict[str, Any] = {}
    used: dict[str, Any] = {
        "at": datetime.now(UTC).isoformat(),
        "message_id": str(message.id) if message is not None else None,
        "arm": None,
        "voice_arm": None,
        "examples": [],
    }
    examples = await learning_bank.retrieve(
        session,
        scope,
        state=state,
        language=language,
        said=said,
        exclude_contact=str(conversation.customer_id) if conversation.customer_id else None,
        embedder=embedder,
        conversation_id=conversation.id,
        canary_percent=canary_percent,
    )
    if examples:
        out["learned_examples"] = [
            {"person": e.person_text, "reply": e.reply_text} for e in examples
        ]
        used["examples"] = [str(e.id) for e in examples]
        await learning_bank.touch(session, examples)
    profile = (conversation.service_brief or {}).get("customer_profile") or {}
    about = " . ".join([said, str(profile.get("business_type") or "")])
    await learning_packs.note_shadow(session, scope, conversation.id, about)
    if pack_brief := await learning_packs.live_brief(session, scope, about):
        out["learned_pack"] = pack_brief
    banned = await learning_lessons.never_say(session, scope, state, language)
    if banned:
        out["never_say"] = banned
    lessons = await learning_lessons.relevant(session, scope, state, language)
    if lessons:
        out["lessons"] = [lesson.text for lesson in lessons]
    latest = noted[-1] if noted else None
    slot = learning_arms.slot_for(list(latest.get("missing") or [])) if latest else None
    if slot is not None:
        await learning_arms.ensure_seeded(session, scope)
        arm = await learning_arms.choose(session, scope, slot, language)
        if arm is not None:
            out["question_hint"] = {"slot": slot, "wording": arm.text}
            used["arm"] = str(arm.id)
    if moment := learning_voice.moment_of(said, state, has_notes=bool(noted)):
        await learning_voice.ensure_seeded(session, scope)
        variant = await learning_voice.choose(session, scope, moment, language)
        if variant is not None:
            out["voice_hint"] = {"moment": moment, "wording": variant.text}
            used["voice_arm"] = str(variant.id)
    if solution_mode:
        out.update(await solution_context.build(session, scope, conversation, said, noted, used))
    if (
        used["arm"]
        or used["examples"]
        or used["voice_arm"]
        or used.get("ideas")
        or used.get("unmatched")
    ):
        brief = dict(conversation.service_brief or {})
        brief["learning_used"] = [
            *list(brief.get("learning_used") or [])[-(STAMPS_KEPT - 1) :],
            used,
        ]
        conversation.service_brief = brief
    return out
