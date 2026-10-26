# ruff: noqa: E501  (Roman Urdu lines read better unbroken)
"""Roman Urdu is pi's weakest language, so every Roman Urdu line pi can say gets the same checklist:
the owner-approved golden replies and the fixed lines shipped in the code (greeting, fallbacks,
safety, offer, quote and follow-up lines).

Checklist (one test each, over every line):
1. no English fragments: no English word that is not a loan word the owner uses ("quote", "payment",
   "team", ...), and no sentence opening with an English filler ("Noted.", "Thanks.", "Sure.");
2. neutral first person and the "aap" forms, common spellings (the linter's `roman_urdu_tone`);
3. short sentences: 24 words at most;
4. everyday words: none of the stiff bookish words in STIFF;
5. at most one question, and when there is one it is the last sentence.
"""

import importlib
import re

import pytest

from app.modules.pi import constitution
from app.modules.pi.golden_replies import GOLDEN
from app.modules.pi.language import ENGLISH

TABLES = {
    "constitution": ("OPENING", "AI_ANSWER", "FALLBACK_LISTENING", "FALLBACK_OTHER", "FIRST_INVITE"),
    "decisions": ("TEXT", "CONSENT_ASK", "COST_ANSWER"),
    "safety": (
        "EMERGENCY_TEXT", "PII_TEXT", "ADVICE_TEXT", "HANDBACK_TEXT", "OPT_OUT_TEXT", "IDENTITY_TEXT",
        "BOUNDARY_TEXT", "ASKS_WHAT_PROBLEM", "ENQUIRY_TEXT", "NORI_TEXT", "ABUSE_TEXT", "NOT_SERVED_TEXT",
    ),
    "solution_ask": ("OFFER_AFTER",),
    "service_conversation": (
        "DISCLOSURE_LINE", "NO_IDEA_LINES", "NO_MORE_IDEAS", "CONSENT_QUESTION", "SEND_QUESTION", "WELCOME_BACK",
    ),
    "followup_policy": ("MESSAGES",),
    "problems": ("SUMMARY_TEXT",),
}  # fmt: skip
# loan words and Urdu words that are spelled like English ones
ALLOWED_ENGLISH = frozenset(
    "workzap pi ai nori quote quotes document documents payment card number team business customer "
    "customers video message chat stock sales client idea ideas password pin otp code id bank transfer "
    "offer account whatsapp meta cctv vision starter growth enterprise plans plan call link update "
    "kickoff proposal invoice invoices details data delete help support read sort project demo "
    "suppliers refund products product recommend endorse model patient setup email "
    "is the me do to so he hi no in an am on".split()  # is/the/me/do/to... are Urdu words too
)
FILLER = re.compile(
    r"(?:^|[.!?]\s+)(?:noted|thanks|thank you|sure|okay|ok|alright|great|perfect)\b", re.I
)
OFFER = "Kya aap in sab ke liye solution document aur quote chahenge?"
STIFF = ("maazrat", "mutaalliq", "iqdam", "mushkilaat", "tawajjuh", "mutaabiq", "bilaa")
MAX_WORDS = 24


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from strings(item)


def roman_urdu(value):
    """Every string kept under a "roman_ur" key, at any depth."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "roman_ur":
                yield from strings(item)
            else:
                yield from roman_urdu(item)


def shipped_lines() -> list[tuple[str, str]]:
    lines = []
    for module, names in TABLES.items():
        mod = importlib.import_module(f"app.modules.pi.{module}")
        for name in names:
            table = getattr(mod, name)
            found = list(roman_urdu(table if isinstance(table, dict) else {}))
            if not found and isinstance(table, dict) and "roman_ur" in table:
                found = list(strings(table["roman_ur"]))
            lines += [(f"{module}.{name}", s) for s in found]
    lines += [("golden", reply) for _, language, _, reply in GOLDEN if language == "roman_ur"]
    return lines


LINES = shipped_lines()


def plain(text: str) -> str:
    text = re.sub(r"\{[^}]*\}", " ", text)  # a placeholder
    return re.sub(r"\S+\.ai\S*", " ", text)  # a Workzap link


def ids(lines):
    return [f"{src}:{text[:28]}" for src, text in lines]


def test_there_are_at_least_twenty_roman_urdu_lines_to_check():
    assert len(LINES) >= 20, len(LINES)


@pytest.mark.parametrize(("source", "text"), LINES, ids=ids(LINES))
def test_no_english_fragments(source, text):
    words = re.findall(r"[a-z']+", plain(text).lower())
    english = [w for w in words if w in ENGLISH and w not in ALLOWED_ENGLISH]
    assert not english, (source, english)
    assert not FILLER.search(plain(text)), (source, "an English filler opens a sentence")


@pytest.mark.parametrize(("source", "text"), LINES, ids=ids(LINES))
def test_neutral_first_person_aap_forms_and_spelling(source, text):
    assert constitution.roman_urdu_tone(text, "") == [], source


@pytest.mark.parametrize(("source", "text"), LINES, ids=ids(LINES))
def test_sentences_are_short(source, text):
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", plain(text).strip()):
        assert len(sentence.split()) <= MAX_WORDS, (source, sentence)


@pytest.mark.parametrize(("source", "text"), LINES, ids=ids(LINES))
def test_everyday_words(source, text):
    stiff = [w for w in STIFF if w in text.lower()]
    assert not stiff, (source, stiff)


@pytest.mark.parametrize(("source", "text"), LINES, ids=ids(LINES))
def test_one_question_and_it_is_last(source, text):
    sentences = [s for s in re.split(r"(?<=[.!?])\s+|\n+", plain(text).strip()) if s.strip()]
    questions = [s for s in sentences if s.rstrip().endswith("?")]
    if text.startswith(OFFER):  # the spec's offer: the question, "you can say no", then what it is
        assert len(questions) == 1, source
        return
    assert len(questions) <= 1, (source, questions)
    if questions:
        assert sentences[-1] == questions[0] or text.rstrip().endswith(
            ("Aap mana bhi kar sakte hain.", "Mana bhi kar sakte hain.")
        ), (source, "the question is not last")
