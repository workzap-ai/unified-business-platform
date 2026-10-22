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

from app.modules.pi import learning, learning_arms, learning_bank
from app.modules.pi.language import detect_language
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
) -> dict[str, Any]:
    """`learned_examples` and `question_hint` for this turn (either may be missing)."""
    said = message.body if message is not None and message.body else ""
    language = detect_language(said) or conversation.language or "en"
    language = language if language in ("en", "roman_ur", "ar") else "en"
    state = conversation.flow_state or ""
    out: dict[str, Any] = {}
    used: dict[str, Any] = {
        "at": datetime.now(UTC).isoformat(),
        "message_id": str(message.id) if message is not None else None,
        "arm": None,
        "examples": [],
    }
    examples = await learning_bank.retrieve(
        session,
        scope,
        state=state,
        language=language,
        said=said,
        exclude_contact=str(conversation.customer_id) if conversation.customer_id else None,
    )
    if examples:
        out["learned_examples"] = [
            {"person": e.person_text, "reply": e.reply_text} for e in examples
        ]
        used["examples"] = [str(e.id) for e in examples]
        await learning_bank.touch(session, examples)
    latest = noted[-1] if noted else None
    slot = learning_arms.slot_for(list(latest.get("missing") or [])) if latest else None
    if slot is not None:
        await learning_arms.ensure_seeded(session, scope)
        arm = await learning_arms.choose(session, scope, slot, language)
        if arm is not None:
            out["question_hint"] = {"slot": slot, "wording": arm.text}
            used["arm"] = str(arm.id)
    if used["arm"] or used["examples"]:
        brief = dict(conversation.service_brief or {})
        brief["learning_used"] = [
            *list(brief.get("learning_used") or [])[-(STAMPS_KEPT - 1) :],
            used,
        ]
        conversation.service_brief = brief
    return out
