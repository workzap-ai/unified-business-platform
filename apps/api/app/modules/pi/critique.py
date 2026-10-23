# ruff: noqa: E501  (the prompt reads better in long lines)
"""Draft, critique, revise (pi Brain spec 8.4.4).

After the main model drafts a reply, a small fast model checks it against the person's style, the
anti-robot checklist and one question: does this reply move understanding forward? A reply that
fails is rewritten once by the same retry the linter already uses; if it still fails, the safe
repair runs. It is a switch (`response_rules.brain.critique`, off by default) because it adds one
small model call to every reply. A failed or unavailable critique never blocks a reply.
"""

import json
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("app.pi.critique")

SYSTEM = """You check one draft reply from pi, Workzap's WhatsApp AI, before it is sent. Answer ok=true
unless the draft clearly fails one of these: (1) it repeats the person's words back or says the same
thing as pi's last message; (2) it opens with the same acknowledgement ("Got it", "Noted") pi used in
its last two replies; (3) it is much longer or more formal than the person's own messages (style);
(4) it does not move understanding forward: no new question about their problem and no useful
confirmation; (5) it sounds like a template or a robot. List each failure in a few plain words. Do
not rewrite the reply."""


class Verdict(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ok: bool = True
    issues: list[str] = Field(default_factory=list, max_length=5)


def switched_on(response_rules: dict[str, Any] | None) -> bool:
    return bool(((response_rules or {}).get("brain") or {}).get("critique") is True)


async def critique(manager: Any, scope: Any, context: dict[str, Any], reply: str) -> str | None:
    """Why the draft should be rewritten, or None when it is fine (or the check could not run)."""
    from app.ai.types import Message

    history = [h.get("text", "") for h in (context.get("history") or [])[-4:]]
    material = {
        "draft": reply,
        "latest_customer_message": context.get("latest_customer_message", ""),
        "recent": history,
        "style": context.get("style") or {},
    }
    try:
        result = await manager.complete_structured(
            scope,
            Verdict,
            alias="fast",
            purpose="pi_critique",
            messages=[
                Message.system(SYSTEM),
                Message.user(json.dumps(material, ensure_ascii=False)),
            ],
            temperature=0.0,
            max_tokens=300,
        )
    except Exception:  # noqa: BLE001 - never a reason to hold back a reply
        logger.warning("pi_critique_failed", exc_info=True)
        return None
    verdict = result.value
    if not isinstance(verdict, Verdict) or verdict.ok or not verdict.issues:
        return None
    return "the quality check failed: " + "; ".join(verdict.issues)
