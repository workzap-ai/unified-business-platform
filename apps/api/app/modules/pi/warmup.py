# ruff: noqa: E501
"""The opening: warm-up and learning the business (platform spec v1.4, Part 16).

For an unhurried first-time owner who opens with a plain "Hi", pi does not start with "what is
going wrong?". It says it is an AI, asks ONE identity question (the business and what it does: the
one allowed two-part question, spec 16.2 and decision 7), asks ONCE for a public page, takes a quick
look when one is given, says back what it understood (labelled as coming from the page), and only
then asks the problem question, soft and open. At most three warm-up questions; skippable; never
pushes for the link; a hurried or direct owner (the first message already says something) skips it.

Off unless `response_rules.brain.warmup` is true. Pure functions: the state lives on the brief
(`brief["warmup"]`), the profile on `brief["business_profile"]`. No model call, so the fixed lines
are in the languages pi writes in Latin letters (English and Roman Urdu; others are translated by
the same step as every other fixed line).
"""

import re
from dataclasses import dataclass
from typing import Any

from app.modules.pi import business_profile, public_page

IDENTITY_ASKED = "identity_asked"
PAGE_ASKED = "page_asked"
DONE = "done"
SKIPPED = "skipped"

IDENTITY = {
    # No language offer: pi answers in the language the owner writes in, as before (the owner asked
    # for the "English or Urdu" line to be removed, 2026-10-27).
    "en": "Hi, I'm pi, an AI from Workzap. First, a little about your business: what is it called, "
    "and what does it do?",
    "roman_ur": "Hi, main pi hoon, Workzap ka AI. Pehle thora aap ke karobar ke baare mein: naam "
    "kya hai, aur kis cheez ka hai?",
}
PAGE_ASK = {
    "en": "If you have a website or an Instagram page, send the link and I'll take a look so I "
    "understand your business better. I only look at public pages. If you have none, no problem.",
    "roman_ur": "Agar website ya Instagram page hai to link bhej dein, main ek nazar daal kar aap ke "
    "karobar ko behtar samajh loon. Sirf public page dekha jaye ga. Na ho to koi baat nahi.",
}
DOOR = {
    "en": "Now tell me, what feels heaviest in your business these days?",
    "roman_ur": "Ab bataiye, in dino sab se zyada kya bhaari lag raha hai?",
}
LOOKED = {  # the page gave no more than a name: nothing to say back
    "en": "I had a look at the page.",
    "roman_ur": "Page par ek nazar daal li.",
}
NO_LINK = {"en": "That's fine.", "roman_ur": "Theek hai."}
CANNOT_OPEN = {
    "en": "That page won't open, no problem.",
    "roman_ur": "Ye page khul nahi raha, koi baat nahi.",
}
SCREENSHOT = {
    "en": "I can't read that page myself; a screenshot works too if you like.",
    "roman_ur": "Ye page main khud nahi parh sakta; chahein to screenshot bhej dein.",
}
ONLY_BUSINESS = {
    "en": "I only look at business pages; tell me about your business in your own words.",
    "roman_ur": "Main sirf karobar ke pages dekhta hoon; aap apne karobar ke baare mein khud bata dein.",
}

# A message that already states a problem is a hurried or direct owner (16.7): no warm-up.
PROBLEM_WORDS = re.compile(
    r"\b(?:masla|masle|problem|issue|nahi\s+(?:ho|hota|aa|bik)|kam\s+ho|loss|nuqsan|stock|"
    r"sale|sales|cash|udhaar|staff|pareshan|tang|mushkil|trouble|struggling|help|madad|"
    r"solution|hal)\b",
    re.IGNORECASE,
)
NO_WEBSITE = re.compile(
    r"\b(?:no|nahi|nahin|none|nai)\b(?:\s+\w+){0,3}\s*\b(?:website|site|page|link|instagram|facebook)\b|"
    r"\b(?:website|site|page|link)\b(?:\s+\w+){0,2}\s+\b(?:nahi|nahin|nai|no)\b|"
    r"\b(?:koi|kuch)\s+nahi\b",
    re.IGNORECASE,
)
URL = re.compile(r"https?://[^\s<>\"')\]]+|(?:www\.)[^\s<>\"')\]]+", re.IGNORECASE)


@dataclass
class Plan:
    """What the warm-up does with this turn: the fixed reply and the state it leaves behind."""

    reply: str
    state: dict[str, Any]
    profile: dict[str, Any]
    ask_page: str = ""  # a link to take a quick look at (the runtime does it before the turn)


def enabled(response_rules: dict[str, Any] | None) -> bool:
    return ((response_rules or {}).get("brain") or {}).get("warmup") is True


def language_key(context: dict[str, Any]) -> str:
    return "roman_ur" if context.get("reply_language") == "roman_ur" else "en"


def link_in(text: str) -> str:
    found = URL.findall(text or "")
    if not found:
        return ""
    url = str(found[0]).rstrip(".,;:!?")
    return url if url.startswith("http") else "https://" + url


def states_problem(said: str) -> bool:
    return bool(PROBLEM_WORDS.search(said or ""))


def _grow(profile: dict[str, Any], said: str) -> dict[str, Any]:
    """The owner's own words about what the business is (kept short, never a name of a person)."""
    business_profile.add_fact(profile, "what_they_do", said[:200], business_profile.OWNER)
    return profile


def plan(context: dict[str, Any]) -> Plan | None:
    """The warm-up reply for this turn, or None to let pi answer normally (the warm-up is skipped,
    done, or not for this chat)."""
    if not (context.get("warmup") or {}).get("enabled"):
        return None
    brief = context.get("brief") or {}
    state = dict(brief.get("warmup") or {})
    step = state.get("step")
    said = str(context.get("latest_customer_message") or "").strip()
    lang = language_key(context)
    profile = dict(brief.get("business_profile") or business_profile.new_profile())
    if step in (DONE, SKIPPED):
        return None
    if step is None:
        if context.get("noted_problems") or context.get("returning_customer"):
            return None  # not a first-time owner: use the profile, no opening (16.7)
        if not context.get("greeting_only"):
            return Plan("", {"step": SKIPPED}, profile)  # a first message with content: no warm-up
        return Plan(IDENTITY[lang], {"step": IDENTITY_ASKED, "asked": 1}, profile)
    if states_problem(said):
        return Plan("", {**state, "step": SKIPPED}, profile)  # they went straight to the problem
    if step == IDENTITY_ASKED:
        if context.get("greeting_only"):
            # "Hi" again is not an answer (live 2026-10-27: the second "Hi" was taken as the
            # business and the page was asked for): ask the identity question once more.
            return Plan(IDENTITY[lang], state, profile)
        profile = _grow(profile, said)
        if url := link_in(said):
            return Plan("", {**state, "step": PAGE_ASKED, "asked": 2}, profile, ask_page=url)
        return Plan(PAGE_ASK[lang], {**state, "step": PAGE_ASKED, "asked": 2}, profile)
    if step == PAGE_ASKED:
        return _after_page(context, state, profile, said, lang)
    return None


def _after_page(
    context: dict[str, Any], state: dict[str, Any], profile: dict[str, Any], said: str, lang: str
) -> Plan:
    done = {**state, "step": DONE}
    look = context.get("page_look")
    if isinstance(look, dict):
        result = public_page.PageResult(**{k: v for k, v in look.items() if k in _FIELDS})
        if result.ok:
            business_profile.from_page(profile, result)
            line = business_profile.say_back(profile, lang) or LOOKED[lang]
            return Plan(f"{line} {DOOR[lang]}".strip(), done, profile)
        note = {"needs_screenshot": SCREENSHOT, "refused": ONLY_BUSINESS}.get(
            result.status, CANNOT_OPEN
        )
        return Plan(f"{note[lang]} {DOOR[lang]}", done, profile)
    if link_in(said):  # a link that the runtime could not look at (no network): say so calmly
        return Plan(f"{CANNOT_OPEN[lang]} {DOOR[lang]}", done, profile)
    if NO_WEBSITE.search(said):
        business_profile.no_website(profile)
    return Plan(f"{NO_LINK[lang]} {DOOR[lang]}", done, profile)  # one ask, once: never again


_FIELDS = set(public_page.PageResult.__dataclass_fields__)
