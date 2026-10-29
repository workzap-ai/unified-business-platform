"""A small, separate call that writes down the problem a person just described, for the turns
where the reply model did not (seen live, 2026-10-24: a model that says "I've noted it" and
returns no problem record roughly one turn in two, so nothing reached the summary, the ideas or the
document). The reply model's own problem notes always win; this only fills a gap.

The call is cheap: one short prompt (the last few things the person said, the titles already
noted, the category list) against the fast alias, instead of sending the whole 26k-token prompt back
for a rewrite. What it returns goes through the same `problems.check_ops` as any other note.
"""

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.pi import taxonomy
from app.modules.pi.problems import ProblemNote, ProblemOp, check_ops

logger = logging.getLogger(__name__)

MIN_WORDS = 5
MAX_NOTES = 8  # a list of problems in one message is one problem each (spec v1.5, 18.6)
MAX_MESSAGE_CHARS = 2000

SYSTEM = """You read what a small-business owner told an assistant on WhatsApp and write down the
business problems in it, in the exact shape asked for. Rules:
- Only problems the person actually describes: something costly, slow, lost, manual, unclear or
  broken in their business. A greeting, thanks, a yes or no, a question about the assistant, or
  a request with no problem in it gives an empty list.
- A request for software or a service still has a problem behind it (a cost, a delay, a manual
  job): note that problem, never the product.
- title: English, at most 8 words, starts with the subject, no names, no blame, no solution words.
- title_local: the same in the person's language and script (Roman Urdu stays in Roman letters,
  never Urdu script).
- user_words: their own words, verbatim, 1 to 3 short pieces. A reason the problem hurts ("parents
  feel bad when we call", "we only collect in the first week") is a detail of it: keep it in
  user_words, and when it is a separate pain make it a second problem. Never drop it because the
  first problem is already noted.
- category and subtype: choose from the list given; leave subtype empty if none fits.
- where, of_total, frequency, impact_types, money_text: only what they said; otherwise empty.
- Never write a person's name; use roles. Do not repeat a problem already noted.
Return the list of problems as the field "found"."""


class SimpleNote(BaseModel):
    """The few fields the extractor is asked for: a small shape the model fills reliably (the full
    ProblemNote, with its thirty fields, came back as invalid output on some turns)."""

    model_config = ConfigDict(extra="ignore")
    title: str = ""
    title_local: str = ""
    user_words: list[str] = Field(default_factory=list)
    summary: str = ""
    category: str = ""
    subtype: str = ""
    where: list[str] = Field(default_factory=list)
    frequency: str = ""

    def to_note(self) -> ProblemNote:
        return ProblemNote(**self.model_dump())


class Extracted(BaseModel):
    model_config = ConfigDict(extra="ignore")
    found: list[SimpleNote] = Field(default_factory=list, max_length=MAX_NOTES)


def category_list() -> str:
    return "\n".join(f"{c.key}: {' '.join(c.subtypes)}" for c in taxonomy.CATEGORIES)


def wants_extraction(context: dict[str, Any], reply: str, ops: list[Any]) -> bool:
    """When to ask: brain mode, no problem record from the reply model, and the person said
    something long enough to hold a problem (not a question to pi, not a greeting)."""
    if context.get("pi_mode") != "brain" or ops:
        return False
    state = (context.get("flow") or {}).get("state", "")
    if state not in (
        "S1_LISTENING",
        "S2_CLARIFYING",
        "S3_NOTED",
        "S4_SORTED_SUMMARY",
        "S_LISTEN_THINK",
    ):
        return False
    said = str(context.get("latest_customer_message", ""))
    if len(re.findall(r"\w+", said)) < MIN_WORDS:
        return False
    if "solution_howto" in context:
        return False
    if (context.get("solution_asked") or context.get("solution_asked_no_ideas")) and context.get(
        "noted_problems"
    ):
        return False  # "give me a solution" about problems already noted: nothing new to note
    # A first message that tells the problems AND asks for a fix ("...can you help me find a
    # solution?") must still note them: the ideas never replace noting.
    return True


async def extract(manager: Any, scope: Any, context: dict[str, Any]) -> list[ProblemOp]:
    """Create-ops for the problem(s) in the person's latest words, or [] (never raises)."""
    history = [
        str(h.get("text", ""))[:400]
        for h in (context.get("history") or [])
        if h.get("role") == "customer"
    ][-3:]
    said = str(context.get("latest_customer_message", ""))
    payload = {
        "latest": said[:MAX_MESSAGE_CHARS],
        "earlier": [t for t in history if t != said][-2:],
        "already_noted": [p.get("title", "") for p in context.get("noted_problems") or []][:12],
        "language": context.get("reply_language") or "en",
        "country": context.get("customer_country") or "",
        "categories": category_list(),
    }
    try:
        from app.ai.types import Message

        result = await manager.complete_structured(
            scope,
            Extracted,
            alias="fast",
            purpose="pi_problem_extract",
            messages=[
                Message.system(SYSTEM),
                Message.user(json.dumps(payload, ensure_ascii=False)),
            ],
            temperature=0.1,
            max_tokens=1500,
        )
    except Exception:  # noqa: BLE001 - an extra call must never fail the reply
        logger.warning("pi_problem_extract_failed", exc_info=True)
        return []
    value = result.value
    notes = value.found if isinstance(value, Extracted) else []
    known = {str(p.get("title", "")).lower() for p in context.get("noted_problems") or []}
    ops = [
        ProblemOp(op="create", note=note.to_note())
        for note in notes[:MAX_NOTES]
        if note.title.strip() and note.title.strip().lower() not in known
    ]
    known_refs = {p["ref"] for p in context.get("noted_problems") or []}
    # The same checks as any note, one note at a time: a bad one is dropped and never stored, but it
    # does not take the good ones with it (Live Audit 5, A52).
    return [op for op in ops if not check_ops([op], known_refs, True)]
