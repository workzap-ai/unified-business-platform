# ruff: noqa: E501  (long regexes read better on one line)
"""What the person does after pi gave them ideas, and what each reaction is worth
(Addendum 2 to the pi Brain v3, Part 3.2).

Pure functions. A reaction scores the ideas pi gave and adds to the reward model
(`learning.IDEA_REWARDS`). Whether the person accepts the offer, approves a quote or pays is not a
reaction and is not here: `score_of` ignores those signals even if a caller passes them, so pi
learns to give better ideas and never to push harder (Part 3.2 and 3.6).
"""

import re
from dataclasses import dataclass

from app.modules.pi import learning, style

# Checked in this order: a clear "it worked" or "it did not help" beats a polite "good idea".
_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "idea_worked",
        re.compile(
            r"\b(?:it worked|that worked|worked for me|kaam kiya|kaam kar gaya|farq para|farq pada|log aa rahe|"
            r"customers aa rahe|results aa rahe|ho gaya (?:kaam|farq)|sales barh)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "idea_no_help",
        re.compile(
            r"\b(?:(?:i |we |maine |humne |hum ne )?(?:tried|try kiya|kar ke dekha|kiya tha)[^.?!]{0,40}(?:didn'?t|did not|nahi|no)\s*(?:help|work|farq|fayda)|"
            r"didn'?t help|did not help|koi farq nahi|fayda nahi|faida nahi|no change|kuch nahi hua|"
            r"(?:kaam|kam) nahi (?:aya|aaya|ayi|aai|kiya|kar (?:raha|rahi|rha|rhi))|nahi chala|chala nahi|"
            r"(?:koi )?result nahi (?:aya|aaya)|farq nahi (?:pada|para|hua))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "idea_generic",
        re.compile(
            r"\b(?:sab ko pata hai|sabko pata hai|ye to sab|everyone knows|too generic|too obvious|"
            r"kuch naya batao|kuch naya bataiye|something new|tell me something new|obvious hai|"
            r"(?:pasand|psnd|pasnd|psand|pasan)\s*(?:nahi|nahin|nai|nhi|nh|ni)|(?:acha|achi|achay|theek|thik|"
            r"sahi)\s*(?:nahi|nahin|nai|nhi|nh|ni)\s*(?:lag|hai|he)|bekar|bekaar|useless|"
            r"not (?:useful|helpful|good|great)|(?:don'?t|do not|didn'?t) like|kaam ke nahi)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "idea_not_possible",
        re.compile(
            r"\b(?:ye nahi ho sakta|nahi ho sakta hamare|hamare liye nahi|humare liye nahi|not possible for us|"
            r"can'?t do (?:that|this)|won'?t work for us|ye hamare bas ka nahi)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "idea_already_doing",
        re.compile(
            r"\b(?:pehle se (?:kar|hai|karte)|ye to (?:hum )?(?:pehle se )?karte|already (?:doing|do|did|have|done)|"
            r"we already|i already|ye pehle se|pehle se ho raha|already (?:kar|kr|ho|chal|use)\w*|"
            r"(?:pehle|pehlay) (?:hi|bhi) (?:se )?(?:kar|kr)\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        # "Did anything start?" answered with no (Part 3.3): not a score, a cue to ask once what got
        # in the way. Worth 0, never a signal in the reward model.
        "idea_not_tried",
        re.compile(
            r"\b(?:abhi tak nahi|abhi nahi kiya|nahi kiya|nahi ho saka|time nahi mila|waqt nahi mila|"
            r"not yet|haven'?t (?:tried|started|done)|did ?n'?t (?:try|get to|start)|couldn'?t get to|"
            r"nahi shuru|shuru nahi)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "idea_impatient",
        re.compile(
            r"\b(?:jaldi|bas karo|time waste|waste of time|enough|stop asking|sawal hi|kitne sawal|"
            r"too many questions|itne sawal)\b|😡|🤬",
            re.IGNORECASE,
        ),
    ),
    (
        "idea_followup",
        re.compile(
            r"\b(?:ye kaise|kaise hoga|kaise karna|kitna time|kitna waqt|how (?:would|does|do|long|exactly)|"
            r"how will that|what would that involve)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "idea_more",
        re.compile(
            r"\b(?:aur (?:bata|batao|bataiye|btao|kuch)|tell me more|more ideas|any other|koi aur idea|"
            r"aur ideas|what else can)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "idea_will_try",
        re.compile(
            r"\b(?:ye karta h|ye karti h|karta hoon|karti hoon|karta hun|karti hun|kal se|good idea|acha idea|"
            r"achha idea|theek hai[, ]+(?:kal|main|hum)|i'?ll try|i will try|we'?ll try|let me try|try karta|"
            r"try karte|shuru karta|shuru karte|makes sense|sahi hai|ye sahi)\b",
            re.IGNORECASE,
        ),
    ),
)
OK_ONLY = re.compile(
    r"^\W*(?:ok|okay|k|hmm+|hm+|acha|accha|theek|thik|oh|ji|haan|han)\W*$", re.IGNORECASE
)

SCORES = learning.IDEA_REWARDS
# Said once, "generic" and "already" mark the idea (and for "already", this business too).
FLAGS = {
    "idea_generic": "generic",
    "idea_already_doing": "already",
    "idea_no_help": "no_help",
    "idea_worked": "worked",
    "idea_will_try": "will_try",
}
# Never part of the solution score, whatever a caller passes (Part 3.2 "Not part of the score").
SALES_SIGNALS = learning.NEVER_REWARDED | {
    "offer_accepted",
    "offer_declined",
    "offer_made",
    "document_sent",
    "quote_approved",
    "quote_accepted",
    "paid",
    "payment_confirmed",
}


@dataclass(frozen=True)
class Reaction:
    signal: str
    score: int
    flag: str  # "" or one of FLAGS' values


def classify(text: str, *, new_problems: bool = False) -> Reaction | None:
    """The reaction in what the person said right after pi's ideas, or None when it says nothing
    about them (a plain acknowledgement with new detail is not a reaction)."""
    said = " ".join((text or "").split())
    if not said:
        return None
    for signal, pattern in _RULES:
        if pattern.search(said):
            return Reaction(signal, SCORES.get(signal, 0), FLAGS.get(signal, ""))
    if style.confused(said):
        return Reaction("idea_confused", SCORES["idea_confused"], "")
    if new_problems:
        return Reaction("idea_new_problems", SCORES["idea_new_problems"], "")
    if OK_ONLY.search(said):
        return Reaction("idea_ok_only", SCORES["idea_ok_only"], "")
    return None


def score_of(signals: list[str]) -> int:
    """The solution score of a list of signals. Sales outcomes never count."""
    return sum(SCORES.get(s, 0) for s in signals if s not in SALES_SIGNALS)


def reaction_of_memory(signal: str) -> str:
    """The value kept in solution memory for a signal: engaged, tried, rejected, generic or none."""
    return {
        "idea_will_try": "tried",
        "idea_worked": "tried",
        "idea_followup": "engaged",
        "idea_more": "engaged",
        "idea_new_problems": "engaged",
        "idea_already_doing": "rejected",
        "idea_not_possible": "rejected",
        "idea_no_help": "rejected",
        "idea_generic": "generic",
    }.get(signal, "none")
