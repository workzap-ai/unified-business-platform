# ruff: noqa: E501
"""Free ideas from the model's own sense, for a problem no industry entry covers (Addendum 2).

The industry entries (Part 4) are the first source of free ideas. When a person asks for a fix and
nothing in the entries fits (no industry yet, a trade the entries do not name, the problem told in
the same message as the ask), pi used to say "I have no quick idea". The model can give a practical
one, so it is asked for two, and every one goes through the same guard as a seed idea: one plain
sentence, no tool or product, no number or promise, no steps, no advice that needs a licence
(medical, legal, tax, veterinary), nothing from the industry's never-say list. What does not pass
is dropped; when nothing passes the caller falls back to the plain "the document covers it" line.
"""

import json
import re
from typing import Any
from uuid import UUID

from app.ai.manager import LLMManager
from app.ai.types import Message
from app.modules.pi import solution_rules
from app.shared.scope import WorkspaceScope

RULES = """You give FREE quick ideas for pi, a WhatsApp business assistant, to say to the owner of a
small or medium business in Pakistan, the UAE or Canada who asked "what can I do about this?".
Give exactly two ideas, written in plain English (they are translated for the owner later). Each:
- is ONE sentence of 12 to 24 words: what to do, a comma, then "so" and the benefit in the owner's own terms;
- can be done this week by the owner or staff with what they already have: a notebook, a phone they
  own, a chat group, a walk round the premises. Nothing to buy, install or set up;
- is specific to the problem the owner described, not generic advice;
- names no app, software, spreadsheet, template, dashboard, tool, brand or vendor;
- has no digits, no percentage, no amount, no promised result;
- has no steps, no settings, no wording to copy;
- asks no question and asks for no names, phone numbers, ID or card details;
- gives no medical, veterinary, legal, tax or financial advice, and nothing about doses, feed
  formulas, treatment, filings or investments;
- never contains anything from the never_say list.
The business and the problem are set by owner_first_message and problems_noted: when the latest
message names none ("more ideas", "aur idea"), give ideas for THAT business and problem, never for
another trade, and never a stock, profit or general-business idea unless that is the problem.
Build each idea from the owner's own words and nouns (their products, animals, orders, files,
people, places): an idea that would fit any business is not an idea. Do not use the stock patterns
"count X from one busy day" or "assign one person at a fixed time"; say what is different for THIS
problem. One idea looks at something to see the real size of the problem, the other changes how a
specific thing is done or kept.
Answer with a JSON object only: {"ideas": ["first idea", "second idea"]}"""

JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def parse(text: str) -> list[str]:
    """The ideas of the model's answer, or an empty list when it is not the expected JSON."""
    found = JSON_OBJECT.search(text or "")
    if not found:
        return []
    try:
        data = json.loads(found.group(0))
    except json.JSONDecodeError:
        return []
    ideas = data.get("ideas") if isinstance(data, dict) else None
    return [str(i).strip() for i in ideas if str(i).strip()][:4] if isinstance(ideas, list) else []


def vetted(ideas: list[str], said: str, never_say: list[str]) -> list[str]:
    """At most two ideas that pass pi's own idea guard and the industry's never-say list."""
    kept: list[str] = []
    for idea in ideas:
        verdict = solution_rules.check_idea(idea, said)
        if verdict.reject or verdict.review:
            continue  # a person decides about money or a regulated topic: never served unreviewed
        if never_say and solution_rules.never_say_hit(idea, never_say):
            continue
        if idea not in kept:
            kept.append(idea.rstrip(". ") + ".")
        if len(kept) == 2:
            break
    return kept


async def free_ideas(
    manager: LLMManager,
    scope: WorkspaceScope,
    *,
    alias: str,
    conversation_id: UUID | None,
    said: str,
    earlier: list[str],
    industry: str | None,
    never_say: list[str],
    already_said: list[str] | None = None,
    problems: list[str] | None = None,
) -> list[str]:
    """Two vetted ideas for what the person described, or [] (the model failed or nothing passed)."""
    user = json.dumps(
        {
            "owner_latest_message": said,
            "owner_first_message": (earlier[:1] or [""])[0][:500],
            "problems_noted": [p[:120] for p in (problems or [])[-4:]],
            "owner_earlier_messages": earlier[-4:],
            "industry": industry or "not known yet",
            "never_say_list": never_say[:8],
            "pi_already_said_do_not_repeat_or_reword": (already_said or [])[-8:],
        },
        ensure_ascii=False,
    )
    try:
        response: Any = await manager.complete(
            scope,
            alias=alias,
            purpose="pi_free_ideas",
            messages=[Message.system(RULES), Message.user(user)],
            max_tokens=1500,
            conversation_id=conversation_id,
        )
    except Exception:  # noqa: BLE001 - the caller has a plain fallback
        return []
    return vetted(parse(str(getattr(response, "text", "") or "")), said, never_say)
