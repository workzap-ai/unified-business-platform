# ruff: noqa: E501  (phrase banks read better one alternative per line)
"""An owner who asks whether Workzap can build the whole thing (Artwing Studios, 2026-10-30).

Three small pieces, all inside the platform spec (Book 5, 5.4, exception R3: "can Workzap do it"):

* `asks_can_you_do`: the Roman Urdu, Urdu and English ways of saying "will you do all this for us"
  that the R3 pattern in `box_signals` did not read ("aap ye sab kaam kar denge hamein").
* `note` / `open_ask`: the ask is kept in the brief, so a later turn ("we already do these") does not
  lose it. It stays open until the offer is made or declined.
* `tried_and_failed`: what the owner said they already do or that did not help, handed to the expert
  as a list, so it is not offered back.

Pure functions. Nothing here reads the database or sends a message.
"""

import re
from typing import Any

BRIEF_KEY = "asked_can_you_do"

# "Will you do all this for us" in the owner's own words. Whole-thought phrases only: "aap" must be
# followed within a short stretch by "kar/bana" + a future or request form, so "aap kya karte hain"
# (what do you do) and "main kar sakta hoon" (what I can do) do not count.
ASKS_CAN_YOU_DO = re.compile(
    r"\b(?:aap|ap|aap log|aap ki team|workzap)\b[^.?!\n]{0,30}?\b(?:kar|bana|karwa|banwa)\s?(?:denge|dengay|dein ge|den ge|doge|do ge|dengi|dogay|de sakte|de sakta)\b"
    r"|\b(?:can|could|will|would) (?:you|workzap|your team) (?:please )?(?:do|build|make|set up|create|handle|run) (?:all|everything|the whole|this whole|a whole|an? (?:entire|complete|full)|the entire)\b"
    r"|\bset (?:this|it|all (?:of )?this|everything) up for us\b"
    r"|\b(?:build|make|create) (?:us|this for us) (?:an? |the )?(?:whole|entire|complete|full)\b"
    r"|آپ[^.?!\n]{0,30}?(?:کر|بنا)\s?(?:دیں گے|دیں گی|دو گے|سکتے)",
    re.IGNORECASE,
)

# The sentence the reply carries when the ideas are used up but the owner asked for the whole thing:
# it says what was heard, never promises a result, and has no question (the offer line that follows
# is the one question, and the last sentence).
HEARD_LINES = {
    "en": "I hear you: you want the whole system, not a few tips.",
    "roman_ur": "Baat saaf hai: aap ko chand tips nahi, poora system chahiye.",
    "ar": "فهمت: تريد نظاماً متكاملاً وليس مجرد نصائح.",
}


def asks_can_you_do(message: str) -> bool:
    """The owner asks whether Workzap will do (all of) this for them."""
    return bool(ASKS_CAN_YOU_DO.search(" ".join((message or "").split())))


def note(brief: dict[str, Any], message: str) -> dict[str, Any]:
    """The brief with the ask kept once the owner has made it (any R3 wording, old or new)."""
    from app.modules.pi import box_signals

    if brief.get(BRIEF_KEY) or not box_signals.asks_who_or_how_long(message):
        return brief
    return {**brief, BRIEF_KEY: True}


def open_ask(brief: dict[str, Any] | None) -> bool:
    """The ask was made and the offer has not been made or declined since."""
    brief = brief or {}
    return bool(
        brief.get(BRIEF_KEY)
        and not brief.get("offer")
        and not brief.get("offer_asked")
        and not brief.get("box_declined_at")
        and not brief.get("declined_recently")
    )


def tried_and_failed(owner_messages: list[str]) -> list[str]:
    """The owner's words that say they already do it, or that it did not help (the reward model's
    own detectors, so the two never disagree)."""
    from app.modules.pi import solution_score

    flags = {"idea_already_doing", "idea_no_help", "idea_generic"}
    found: list[str] = []
    for text in owner_messages:
        said = " ".join((text or "").split())
        reaction = solution_score.classify(said) if said else None
        if reaction is not None and reaction.signal in flags:
            found.append(said[:240])
    return found[-4:]
