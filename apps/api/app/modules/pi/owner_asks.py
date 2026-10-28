# ruff: noqa: E501
"""What an owner has told pi they do NOT have, and when they ask to understand the plan.

Live chat 2026-10-28 (a furniture maker): the owner said six times that no records exist ("hum record
nahi rakhte", "exact pata nahi") and pi kept asking for what they had just said they do not have
("kitne orders late hue the?", "kaun sa stage sab se zyada atakta hai?") until the owner wrote "aap
baar baar mujh se woh details pooch rahe hain jo mere paas available nahi hain". Asked for an overall
plan, pi answered in one sentence and asked another question; one reply even handed the lead back
("Aap is ke baare mein aage kya poochna chahenge?").

This module is the rule behind that, for every industry and language pi writes: a fact the owner has
said they do not have is closed; pi proposes what to record from today and leads. Pure functions.
"""

import re
from collections.abc import Sequence

# "we keep no records", "I don't know exactly", "no register": a fact the owner does not have.
NO_RECORDS = re.compile(
    r"\b(?:record|records|data|hisaab|register|excel|rikard)\b.{0,40}\b(?:nahi|nhi|nahin|nai|no|not|"
    r"missing)\b"
    r"|\b(?:nahi|nhi|nahin|no|not)\b.{0,30}\b(?:record|records|register|excel)\b"
    r"|\b(?:exact|sahi|theek)\b.{0,25}\b(?:pata|maloom|malum|number|figure)\b.{0,12}\b(?:nahi|nhi|nahin)\b"
    r"|\b(?:pata|maloom|malum)\s+(?:nahi|nhi|nahin)\b"
    r"|\b(?:andaza|andaaza)\s+(?:nahi|nhi|nahin)\b"
    r"|\bdon'?t\s+(?:know|have)\b|\bdo\s+not\s+(?:know|have)\b|\bno\s+idea\b|\bnot\s+sure\b"
    r"|\bhaven'?t\s+(?:recorded|tracked|kept)\b|\bwe\s+don'?t\s+(?:track|record|keep)\b",
    re.IGNORECASE,
)

# The owner complaining that pi keeps asking.
REPEAT_COMPLAINT = re.compile(
    r"\bbaar\s*baar\b.{0,40}\b(?:pooch|puch|poochh|ask|sawal)\w*"
    r"|\b(?:pooch|puch|poochh|ask)\w*\b.{0,30}\bbaar\s*baar\b"
    r"|\b(?:you|aap)\b.{0,30}\b(?:keep|kar rahe)\b.{0,20}\bask",
    re.IGNORECASE,
)

# A question about what happened before or how often: the very thing an owner with no records cannot
# answer ("pichle mahine ke kitne orders late hue?", "aam tor par kaun sa stage sab se zyada?").
ASKS_HISTORY = re.compile(
    r"\b(?:pichle|pichhle|pehle\s+ke|last\s+(?:month|week|year|time)|previous|past)\b"
    r"|\b(?:aam\s+tor\s+par|aksar|zyada\s+tar|zyadatar|sab\s+se\s+(?:zyada|ziyada)|sab\s+se\s+kam|"
    r"usually|typically|on\s+average|how\s+often|how\s+many\s+(?:times|of)|most\s+(?:often|of\s+the))\b"
    r"|\bkitni\s+baar\b|\bkitne\s+(?:late|orders|log|din)\b.{0,25}\b(?:hue|hui|hoye|the|thi)\b"
    r"|\bpercentage\b|\baverage\b",
    re.IGNORECASE,
)

# Asking pi to explain the plan before anything else.
ASKS_PLAN = re.compile(
    r"\b(?:overall|poora|pura|simple|practical|initial)\b.{0,25}\b(?:plan|system|solution)\b"
    r"|\bplan\b.{0,25}\b(?:samjha|samjhaen|dein|den|do|bata|batayein|explain)\w*"
    r"|\b(?:samjha|samjhaen|samjhayen|explain|bata)\w*\b.{0,40}\b(?:plan|system|solution|kaise)\b"
    r"|\bkaise\s+(?:kaam|chalega|hoga|banega|karega)\b"
    r"|\b(?:pehle|first)\b.{0,30}\b(?:samjha|explain|understand)\w*",
    re.IGNORECASE,
)

NO_RECORDS_RULE = """
THE OWNER HAS SAID THEY DO NOT HAVE SOME FACTS (no records, "pata nahi", "exact nahi"). Treat each as
closed and unknown: never ask for it again, and never ask how many, how often, how much, what usually
or most happens, or what happened last month or before. Do the opposite of interviewing: say, in one
or two plain sentences, what is worth writing down from today (a few simple things, no forms) and
how that will show the answer in a few weeks, then lead with ONE question that moves forward (a
choice, a start, a step they can say yes to), never a fact they just said they lack.
"""

PLAN_RULE = """
THE OWNER ASKED YOU TO EXPLAIN THE PLAN IN SIMPLE WORDS (before any document or quote). Answer it now,
in this message, in plain words: what a first, small version would hold, what each person does day to
day (the worker, the owner), what the owner sees, and what can wait for later. Say what they would
notice, not how it is built; no tool words unless they used them; no price. Short lines are fine
(up to four, each one thought). Do not offer the document or the quote unless they ask. End with ONE
question that moves the plan forward (for example which part to start with); it is never a fact they
said they do not have, and never "what do you want to ask next".
"""

REPEAT_RULE = """
THE OWNER SAYS YOU KEEP ASKING. Do not ask them for any fact in this reply. Say sorry in six words or
fewer, then give what they asked for (the plan or the next step) from what you already know, then ask
nothing, or one question that is a choice they can answer in a word.
"""


def count_unknowns(owner_messages: Sequence[str]) -> int:
    """How many of these owner messages say they do not have some fact."""
    return sum(1 for text in owner_messages if NO_RECORDS.search(text or ""))


def asks_for_history(question: str) -> bool:
    """The question asks about the past or about how often: what an owner with no records lacks."""
    return bool(ASKS_HISTORY.search(question or ""))


def asks_for_plan(said: str) -> bool:
    return bool(ASKS_PLAN.search(said or ""))


def complains_of_repeats(said: str) -> bool:
    return bool(REPEAT_COMPLAINT.search(said or ""))
