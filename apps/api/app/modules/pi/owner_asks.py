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
    r"|\bkaise\s+(?:kaam|chalega|hoga|banega|karega|alert|batayega)\b"
    r"|\b(?:bata|batayein|explain|samjha)\w*\b.{0,100}\b(?:system|alert|reminder)\b.{0,40}\bkaise\b"
    r"|\bsystem\b.{0,40}\b(?:mujhe|hamein|humein)\b.{0,30}\bkaise\b"
    r"|\b(?:pehle|first)\b.{0,30}\b(?:samjha|explain|understand)\w*",
    re.IGNORECASE,
)

# "abhi mujh se aur sawal na karein", "no more questions", "don't ask me anything": no question now.
NO_QUESTIONS = re.compile(
    r"\b(?:aur|koi|mazeed)\s+(?:koi\s+)?sawal\w*\s+(?:na|mat|nahi)\b"
    r"|\bsawal\w*\s+(?:na|mat)\s+(?:karein|kijiye|poochein|pooch\w*|karo|kro|puchein)\b"
    r"|\bmujh\s*se\s+(?:aur\s+)?(?:koi\s+)?sawal\w*\s+(?:na|mat)\b"
    r"|\b(?:no|stop|without)\s+(?:more\s+)?questions\b"
    r"|\bdon'?t\s+ask(?:\s+me)?(?:\s+any)?(?:\s+more)?\s+questions\b"
    r"|\bstop\s+asking\b",
    re.IGNORECASE,
)

# What did we say or decide before? Answered from the chat and the notes, never guessed.
ASKS_RECALL = re.compile(
    r"\byaad\s+(?:nahi|nhi|hai|karwa|kara)\w*"
    r"|\b(?:pehle|pichli\s+baar|pichle)\b.{0,50}\b(?:baat|discuss|decide|plan|chat|tay)\w*"
    r"|\b(?:decide|discuss|tay)\s+(?:kiya|hua|kia)\s+(?:tha|thi|the)\b"
    r"|\bwhat\s+did\s+we\s+(?:decide|discuss|agree|say)\b|\bremind\s+me\b"
    r"|\bdo\s+you\s+remember\b|\blast\s+time\s+we\b"
    r"|\b(?:don'?t|do\s+not|cannot|can'?t)\s+(?:remember|recall)\b|\bforgot(?:ten)?\s+what\b"
    r"|\bwhat\s+(?:was|were)\s+(?:decided|agreed)\b",
    re.IGNORECASE,
)

# Asking pi to suggest or recommend something specific (a list, an option, an approach).
ASKS_SUGGEST = re.compile(
    r"\b(?:suggest|recommend)\w*\b.{0,60}\b(?:list|options?|approach|tareeqa|tareeka|way|plan)\b"
    r"|\b(?:list|options?|tareeqa|tareeka|approach)\b.{0,60}\b(?:suggest|recommend)\w*\b"
    r"|\bkhud\s+(?:suggest|recommend)\w*"
    r"|\b(?:aap|ap)\b.{0,25}\b(?:suggest|recommend)\s*(?:karein|kijiye|kren|kro|karo)\b",
    re.IGNORECASE,
)

NO_QUESTIONS_RULE = """
THE OWNER ASKED YOU NOT TO ASK QUESTIONS (for now). There must be no question mark and no question in
this reply. Answer what they asked, recommend one concrete thing, and lead with a next step said as
a statement ("Pehle ye karte hain: ..."). Do not offer the document or the quote either, which is a
question. If a fact is missing, say what you assume and that they can correct it.
"""

RECALL_RULE = """
THE OWNER ASKS WHAT WAS SAID OR DECIDED BEFORE. Answer only from this conversation and the notes you
can see: a short recap (what is settled, what was left open) in their words and language. What is not
in them, say plainly that you do not have it; never guess or invent. This is a question about the past,
not about how anything is built: do not say "the details are in the document" and do not offer a
document or a quote here.
"""

SUGGEST_RULE = """
THE OWNER ASKED YOU TO SUGGEST OR RECOMMEND something specific (a list, an option, an approach). Do
it in this message, concretely: if a list was asked for, write the list (short lines, up to eight);
if a recommendation was asked for, say which one and why in a line. Do not answer with "ideas to try",
do not hand the choice back, and do not turn it into an offer of a document.
"""

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


_SENTENCE_END = re.compile(r"(?<=[.!?؟۔？。！])\s*(?=\S)|(?<=[.!?؟۔])\s+")
_NO_ASK = re.compile(
    r"^\W*(?:aap\s+)?mana\s+bhi\s+kar\s+sakte\s+hain\W*$|^\W*you\s+can\s+say\s+no\W*$",
    re.IGNORECASE,
)


def asks_for_recall(said: str) -> bool:
    return bool(ASKS_RECALL.search(said or ""))


def asks_to_suggest(said: str) -> bool:
    return bool(ASKS_SUGGEST.search(said or ""))


def asked_no_questions(said: str) -> bool:
    return bool(NO_QUESTIONS.search(said or ""))


def without_questions(reply: str) -> str:
    """The reply with its question sentences taken out (the owner asked for none), and the "you can
    say no" that belongs to an offer. Unchanged when too little would be left to answer with."""
    kept_lines: list[str] = []
    for line in (reply or "").split(chr(10)):
        sentences = _SENTENCE_END.split(line)
        kept = [
            x
            for x in sentences
            if not x.rstrip().endswith(("?", "؟", "？")) and not _NO_ASK.match(x)
        ]
        if kept or not line.strip():
            kept_lines.append(" ".join(kept))
    text = re.sub(r"\n{3,}", chr(10) * 2, chr(10).join(kept_lines)).strip()
    return text if len(text.split()) >= 4 or (" " not in text and len(text) >= 6) else reply
