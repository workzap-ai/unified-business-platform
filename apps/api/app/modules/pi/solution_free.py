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
from app.modules.pi import constitution, solution_rules
from app.modules.pi.language import detect_language
from app.shared.scope import WorkspaceScope

RULES = """You give FREE quick ideas for pi, a WhatsApp business assistant, to say to the owner of a
small or medium business in Pakistan, the UAE or Canada who asked "what can I do about this?".
Give exactly two ideas, written in plain English (they are translated for the owner later). Each:
- is ONE sentence of 12 to 24 words: what to do, a comma, then "so" and the benefit in the owner's own terms;
- can be done by the owner or staff with what they already have: a notebook, a phone they
  own, a chat group, a walk round the premises. Nothing to buy, install or set up;
- is something the OWNER does ("send a clear photo with the price", "ask staff to ..."), never what
  Workzap, pi or "we" would do and never passive ("we can look at", "can be noted", "team ko clear");
- is specific to the problem the owner described, not generic advice;
- when it fits the problem, reflects how customers find and talk to businesses today (short
  videos, a listing and reviews on the online map, chats and photos with customers, an online
  catalogue), always said by kind and never by app or brand name, never a custom from decades ago;
- names no app, software, spreadsheet, template, dashboard, tool, brand or vendor;
- uses plain words a shopkeeper uses: no jargon (bottleneck, workflow, streamline, optimise, leverage,
  touchpoint, KPI);
- has no digits, no percentage, no amount, no promised result;
- names no time or duration at all (no "this week", "today", "tomorrow", "daily", "one week", "a month"):
  pi may not state a timeline;
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
Examples of the right kind (do not copy them; say what fits THIS problem): "Put the rate and how to
order in the first line of every short video caption, so a viewer can act without asking."; "Count the
cash at closing with two people and post the total in one shared chat, so a gap is seen at once.";
"Keep a list of customers who agreed to hear from you and message them when new stock arrives, so
they come back first."; "Send a clear photo, the size chart and one line on delivery together with
the rate, so the buyer has no reason to ask again." When the owner named a channel (a DM, reels, a
chat), use their word for it.
Answer with a JSON object only: {"ideas": ["first idea", "second idea"]}"""

MAX_WORDS = 28
JARGON = re.compile(
    r"\b(?:bottlenecks?|workflows?|streamlin\w*|optimi[sz]\w*|leverag\w*|touchpoints?|kpis?|synerg\w*)\b",
    re.IGNORECASE,
)
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


GENERIC = re.compile(
    r"\b(?:improve|boost|grow|enhance) (?:your )?(?:marketing|sales|business|brand)\b"
    r"|\buse social media\b|\bbuild (?:your )?brand\b|\bstay consistent\b|\bbe patient\b",
    re.IGNORECASE,
)
FACT_PREFIX = 5  # letters compared, so "orders" and "order", "branches" and "branch" count as one


def fact_words(*texts: str) -> set[str]:
    """What the person said, as short word stems an idea can be checked against."""
    found: set[str] = set()
    for text in texts:
        for word in re.findall(r"[^\W\d_]{4,}", (text or "").lower()):
            found.add(word[:FACT_PREFIX])
    return found


def uses_a_fact(idea: str, facts: set[str]) -> bool:
    return not facts or bool(fact_words(idea) & facts)


PRICE_WORD = re.compile(r"\bprices?\b|\bpricing\b", re.IGNORECASE)
PRICE_SETTING = re.compile(
    r"\b(?:set|raise|lower|cut|reduce|increase|change|fix|decide|charge|drop)\s+(?:your\s+|the\s+)?"
    r"(?:prices?|pricing)\b|\bpricing\b|\bwhat\s+price\b",
    re.IGNORECASE,
)


def only_price_talk(idea: str) -> bool:
    """The idea was held for review only because it says "price" (send the price with a photo, share a
    menu with prices): talking about a price is not advice on what price to charge. Any other money
    or regulated word, or advice to set, change or decide a price, still waits for a person."""
    if PRICE_SETTING.search(idea):
        return False
    rest = PRICE_WORD.sub("", idea)
    return bool(solution_rules.check_idea(rest).review == []) and bool(PRICE_WORD.search(idea))


def vetted(
    ideas: list[str], said: str, never_say: list[str], facts: set[str] | None = None
) -> list[str]:
    """At most two ideas that pass pi's own idea guard and the industry's never-say list."""
    kept: list[str] = []
    for idea in ideas:
        verdict = solution_rules.check_idea(idea, said)
        if verdict.reject or (verdict.review and not only_price_talk(idea)):
            continue  # a person decides about money or a regulated topic: never served unreviewed
        if never_say and solution_rules.never_say_hit(idea, never_say):
            continue
        if GENERIC.search(idea) or not uses_a_fact(idea, facts or set()):
            continue  # R-SOL-04: every idea uses something the person said; generic lists are banned
        if len(idea.split()) > MAX_WORDS or JARGON.search(idea):
            continue  # R-VAL-03: one short plain sentence (a long or jargon idea turns to mush in Urdu)
        if constitution.TIMELINE_STRONG.search(idea) or constitution.TIMELINE_WEAK.search(idea):
            continue  # R-HONEST-01: pi never states a time or duration it was not given
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
    # The ideas are written in English, so a fact is checked only against English words: the problem
    # titles pi noted, or an owner who wrote in English. A Roman Urdu or Arabic message alone gives
    # nothing to compare an English idea with.
    english = bool(problems) or detect_language(said) == "en"
    facts = fact_words(said, *earlier[-4:], *(problems or [])) if english else set()
    return vetted(parse(str(getattr(response, "text", "") or "")), said, never_say, facts)
