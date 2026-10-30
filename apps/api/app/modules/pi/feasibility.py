"""Platform spec v1.4, 17.4 check G10 (TS5, A46): an idea must be feasible for THIS owner.

The idea has to be possible with the owner's stated size and resources (people, shops, hours). The
spec's case: "a named on-call person always available" for a business of two technicians who are
both on jobs at night. `resources_of` reads what the owner said about their size; `infeasible`
names the demand an idea makes that those means cannot carry, or None. An idea that fails is
withheld by the idea filter (never reshaped silently into something the owner did not say);
`reshape_hint` tells the model, in the one rewrite, how to fit the idea to the owner's own people.

Pure functions, no model. Nothing is judged when the owner has not stated a size: an unknown size
is not a small one. Used only with `IdeaContext.resources` set (workspaces with `thinking` on).
"""

import re
from dataclasses import dataclass

_NUMBERS = {
    "one": 1,
    "ek": 1,
    "single": 1,
    "two": 2,
    "do": 2,
    "three": 3,
    "teen": 3,
    "four": 4,
    "char": 4,
    "chaar": 4,
    "five": 5,
    "panch": 5,
    "paanch": 5,
    "six": 6,
    "chay": 6,
    "seven": 7,
    "saat": 7,
    "eight": 8,
    "aath": 8,
    "nine": 9,
    "nau": 9,
    "ten": 10,
    "das": 10,
}
_COUNT = r"(?:\d{1,3}|" + "|".join(sorted(_NUMBERS, key=len, reverse=True)) + r")"
_PEOPLE_NOUN = (
    r"(?:technicians?|staff|workers?|employees?|people|persons?|men|guys|members?|drivers?|"
    r"locksmiths?|plumbers?|electricians?|engineers?|mechanics?|cooks?|chefs?|salespeople|"
    r"salesmen|agents?|log|bande|banday|banda|mulazim\w*|karigar\w*|ustad\w*|team members?)"
)
_PEOPLE = re.compile(
    rf"\b({_COUNT})\s+(?:(?:of\s+)?(?:our|my|the)\s+)?(?:\w+\s+)?{_PEOPLE_NOUN}\b", re.IGNORECASE
)
_ALONE = re.compile(
    r"\b(?:just me|only me|me alone|i work alone|i am alone|i'm alone|by myself|solo|one[- ]man|"
    r"main akela|main akeli|akela hi|akeli hi|akele hi|sirf main)\b",
    re.IGNORECASE,
)
_WE_TWO = re.compile(
    r"\b(?:the two of us|both of us|hum (?:dono|do log)|ham dono)\b", re.IGNORECASE
)
_ONE_SITE = re.compile(
    r"\b(?:one|single|only one|ek)\s+(?:shop|store|outlet|branch|dukan|showroom|workshop|office|"
    r"location|kitchen)\b|\b(?:ek hi)\s+(?:shop|dukan|branch|outlet)\b",
    re.IGNORECASE,
)

# What an idea may demand only of a business with enough hands.
_ALWAYS_ON = re.compile(
    r"\b(?:on[- ]?call|24\s*/\s*7|24\s*x\s*7|24 hours|round the clock|around the clock|"
    r"always (?:available|reachable|on)|(?:at )?any time of (?:the )?(?:day|night)|day and night|"
    r"all night|night shift|overnight cover|din raat|har waqt)\b",
    re.IGNORECASE,
)
_DEDICATED = re.compile(
    r"\b(?:dedicated|full[- ]time|separate|own)\s+(?:person|staff|team|manager|employee|"
    r"coordinator|dispatcher|receptionist|assistant|desk|department|call ?cent(?:re|er)|"
    r"operator|supervisor)\b",
    re.IGNORECASE,
)
_EVERY_SITE = re.compile(
    r"\b(?:each|every|all)\s+(?:of\s+(?:the|your)\s+)?(?:branch(?:es)?|outlets?|shops?|stores?|"
    r"locations?|sites?)\b",
    re.IGNORECASE,
)
SMALL = 2  # up to this many people cannot staff an always-on or dedicated role


@dataclass(frozen=True)
class Resources:
    """What the owner said about their size. None: not stated."""

    people: int | None = None
    sites: int | None = None


def _count(token: str) -> int | None:
    token = token.lower()
    return int(token) if token.isdigit() else _NUMBERS.get(token)


def resources_of(owner_words: str) -> Resources:
    """The owner's stated number of people and sites. The smallest stated head count wins (a
    business that says two technicians and, elsewhere, forty customers is a business of two)."""
    text = owner_words or ""
    counts = [c for m in _PEOPLE.finditer(text) if (c := _count(m.group(1))) is not None]
    if _ALONE.search(text):
        counts.append(1)
    if _WE_TWO.search(text):
        counts.append(2)
    people = min(counts) if counts else None
    sites = 1 if _ONE_SITE.search(text) else None
    return Resources(people=people, sites=sites)


def infeasible(idea: str, owner_words: str) -> str | None:
    """What the idea demands that the owner's means cannot carry (a short plain reason), or None."""
    res = resources_of(owner_words)
    if res.people is not None and res.people <= SMALL:
        if _ALWAYS_ON.search(idea):
            return (
                f"it needs someone always available, but the owner has {res.people} "
                "people who are themselves on jobs"
            )
        if _DEDICATED.search(idea):
            return f"it needs a dedicated person or team, but the owner has {res.people} people"
    if res.sites == 1 and _EVERY_SITE.search(idea):
        return "it is about every branch or outlet, but the owner has one place"
    return None


def check(idea: str, owner_words: str) -> str | None:
    """G10 in the idea filter's style: the rule id, or None."""
    return "G10" if infeasible(idea, owner_words) else None


def reshape_hint(idea: str, owner_words: str) -> str:
    """Said to the model in the rewrite: why the idea cannot be carried and how to fit it."""
    why = infeasible(idea, owner_words) or "it needs more people or hours than the owner has"
    return (
        f"G10: {why}. Fit the idea to the owner's own people and hours (for example 'whoever "
        "finishes a job first calls back first', or a message that answers at once), or leave "
        "it out"
    )


def reply_problem(reply: str, owner_words: str) -> str | None:
    """The rewrite reason when a reply's own plan or idea breaks G10 (checked sentence by
    sentence, so one infeasible line is named), else None."""
    for sentence in re.split(r"(?<=[.!?])\s+|[\r\n]+", reply or ""):
        if sentence.rstrip().endswith(("?", "؟")):
            continue  # a question asks about the owner's means; it proposes nothing
        if sentence.strip() and infeasible(sentence, owner_words):
            return reshape_hint(sentence, owner_words)
    return None
