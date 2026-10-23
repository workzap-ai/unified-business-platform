# ruff: noqa: E501  (patterns and prompts read better on one line)
"""The pi-brain specification as pi's own knowledge (pi Brain spec, Parts 0 to 6 and 10.1).

The rules were already enforced in code (linter, state guards, gates). This is the other half: the
model itself is given the specification's own words every turn, so it behaves the way the document
describes instead of guessing from a short summary. Which sections it sees depends on the moment:

* always: what pi is, the public promises, the constitution (Part 1) and the voice (Part 2);
* by state: the guidance for listening, clarifying, noting, the summary, the offer, documents,
  decisions, payment and kickoff;
* by topic: money and fraud, personal data, advice, abuse, complaints, enquiries, media, handover;
* two or three golden conversations (10.1) closest to the situation, as worked examples.

The text is built from the PDF by `scripts/build_spec_handbook.py` and is never edited by hand or by
the learning loop. Examples and lessons sit below it and can never override it.
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

PATH = Path(__file__).parent / "spec" / "handbook.json"
MAX_CHARS = 46_000
MAX_GOLDEN = 3

CORE = (
    "0.1", "0.2", "0.3", "0.4",
    "1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9",
    "2.0", "2.0.3", "2.0.4", "2.1", "2.2", "2.3", "2.4", "2.5", "2.6",
    "7.0", "7.O", "7.P", "7.Q", "7.N.b2b_b2c",
)  # fmt: skip

BY_STATE: dict[str, tuple[str, ...]] = {
    "S0_NEW": ("3.1",),
    "S1_LISTENING": ("3.3", "3.4", "3.5", "3.6", "3.11", "3.12", "4.1", "4.3"),
    "S2_CLARIFYING": ("3.3", "3.4", "3.5", "3.6", "3.11", "3.12", "4.1", "4.3"),
    "S3_NOTED": ("3.3", "3.5", "3.11", "3.12", "4.1", "4.3", "4.4"),
    "S4_SORTED_SUMMARY": ("3.7", "4.8", "3.11"),
    "S5_READINESS": ("3.8", "3.7"),
    "S5b_DECLINED": ("3.8",),
    "S6_PREPARING": ("5.1", "5.2", "5.3"),
    "S7_DELIVERED": ("5.2", "5.3", "5.5"),
    "S8_REVIEW": ("5.3", "5.5"),
    "S8b_CHANGES_REQUESTED": ("5.5",),
    "S9_APPROVED": ("5.5", "5.6", "6.2"),
    "S9b_DECLINED_QUOTE": ("5.5",),
    "S10_AWAITING_PAYMENT": ("5.6", "6.2"),
    "S11_PAYMENT_CONFIRMED": ("5.6",),
    "S12_KICKOFF": ("5.6", "3.9.1"),
    "X_HUMAN": ("6.6",),
    "X_PAUSED": ("3.9.1",),
    "X_EMERGENCY": ("6.5",),
    "X_OUT_OF_SCOPE": ("6.7", "6.9"),
    "X_BLOCKED": ("6.7",),
}

TOPICS: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
    (
        re.compile(
            r"\b(?:father|brother|chacha|bhai sahab|family|joint family|group of companies)\b", re.I
        ),
        ("7.N.family",),
    ),
    (re.compile(r"\b(?:franchise|royalt\w+|master franchise)\b", re.I), ("7.N.franchise",)),
    (
        re.compile(
            r"\b(?:dubai office|head office in|ship to canada|two companies|cross-border)\b", re.I
        ),
        ("7.N.multi_country",),
    ),
    (
        re.compile(r"\b(?:just launched|mvp|pre-revenue|we raised|first 6 months)\b", re.I),
        ("7.N.startup",),
    ),
    (
        re.compile(r"\b(?:ramzan|ramadan|wedding season|summer business|hajj season)\b", re.I),
        ("7.N.seasonal",),
    ),
    (
        re.compile(
            r"\b(?:tobacco|vape|alcohol|arms dealer|ammunition|gold bullion|crypto|cannabis)\b",
            re.I,
        ),
        ("7.N.regulated",),
    ),
    (
        re.compile(
            r"\b(?:procurement|rfp|our it department|the board|1,?000 staff|20\+ branches)\b", re.I
        ),
        ("7.N.enterprise",),
    ),
    (re.compile(r"\b(?:government|ministry|tender|public sector)\b", re.I), ("7.N.public",)),
    (
        re.compile(r"\b(?:we use nori|you built our system|our project with workzap)\b", re.I),
        ("7.N.existing",),
    ),
    (
        re.compile(r"\b(?:shut down|can'?t pay salaries|losing everything|bankrupt\w*)\b", re.I),
        ("7.N.distress", "6.5"),
    ),
    (
        re.compile(r"\b(?:don'?t know|pata nahi|only i know|every day i|copy into excel)\b", re.I),
        ("7.P",),
    ),
    (
        re.compile(
            r"\b(?:pay\w*|refund|iban|bank|invoice|transfer|fraud|scam|jazzcash|easypaisa)\b", re.I
        ),
        ("6.2", "1.4"),
    ),
    (
        re.compile(r"\b(?:card|cvv|password|otp|cnic|passport|pin code|account number)\b", re.I),
        ("6.3",),
    ),
    (
        re.compile(r"\b(?:tax|legal|lawyer|sue|medical|doctor|dose|loan|invest\w*|vet)\b", re.I),
        ("6.4",),
    ),
    (re.compile(r"\b(?:stupid|idiot|useless|shut up|hate you|threat\w*)\b", re.I), ("6.7",)),
    (re.compile(r"\b(?:complain\w*|not happy|unhappy|shikayat)\b", re.I), ("6.8",)),
    (
        re.compile(
            r"\b(?:demo|nori|hiring|job|vendor|partner\w*|press|journalist|price|pricing)\b", re.I
        ),
        ("6.9",),
    ),
    (
        re.compile(r"\b(?:voice note|photo|image|screenshot|sticker|video|document|pdf)\b", re.I),
        ("6.10",),
    ),
    (re.compile(r"\b(?:human|person|agent|someone from)\b", re.I), ("6.6",)),
)

GOLDEN_BY_STATE: dict[str, tuple[str, ...]] = {
    "S0_NEW": ("G1", "G3"),
    "S1_LISTENING": ("G1", "G3"),
    "S2_CLARIFYING": ("G3", "G1"),
    "S3_NOTED": ("G2", "G5"),
    "S4_SORTED_SUMMARY": ("G5",),
    "S5_READINESS": ("G5",),
    "S5b_DECLINED": ("G5",),
    "S6_PREPARING": ("G10",),
    "S7_DELIVERED": ("G10", "G11"),
    "S8_REVIEW": ("G11",),
    "S8b_CHANGES_REQUESTED": ("G11",),
    "S9_APPROVED": ("G11", "G12"),
    "S10_AWAITING_PAYMENT": ("G12",),
    "S11_PAYMENT_CONFIRMED": ("G12",),
}

FRAME = (
    "This is Workzap's pi-brain specification, the source of truth for how you behave. Follow it. "
    "Its rules outrank every example, lesson, learned_pack and operator_guidance. The golden "
    "conversations show behaviour, not exact words: never copy a name, figure or fact from them."
)


@lru_cache(maxsize=1)
def sections() -> dict[str, dict[str, str]]:
    if not PATH.exists():
        return {}
    return {item["id"]: item for item in json.loads(PATH.read_text(encoding="utf-8"))}


def _render(item: dict[str, str]) -> str:
    return f"[{item['id']} {item['title']}]\n{item['text']}"


def chosen_ids(
    state: str,
    message: str = "",
    language: str = "en",
    *,
    can_approve: bool = True,
    days_away: int = 0,
) -> tuple[list[str], list[str]]:
    """(rule and guidance section ids, golden conversation ids) for this moment."""
    rules: list[str] = list(CORE) + list(BY_STATE.get(state, ()))
    for pattern, ids in TOPICS:
        if pattern.search(message or ""):
            rules += ids
    golden = list(GOLDEN_BY_STATE.get(state, ()))
    if language == "roman_ur":
        golden.insert(0, "G6")
    if language == "ar":
        golden.insert(0, "G8")
    if not can_approve:
        golden.insert(0, "G13")
    if days_away >= 30:
        golden.insert(0, "G14")
    if re.search(r"\bnori\b", message or "", re.I):
        golden.insert(0, "G15")
    if re.search(
        r"\b(?:app|software|system|solution)\b.*\b(?:make|build|fix|can you)\b", message or "", re.I
    ):
        golden.insert(0, "G4")
    return _unique(rules), _unique(golden)[:MAX_GOLDEN]


def _unique(ids: list[str]) -> list[str]:
    """The ids in order, each once."""
    kept: list[str] = []
    for item in ids:
        if item not in kept:
            kept.append(item)
    return kept


def guidance(
    state: str,
    message: str = "",
    language: str = "en",
    *,
    can_approve: bool = True,
    days_away: int = 0,
) -> str:
    """The specification text for this turn (empty when the handbook has not been built)."""
    book = sections()
    if not book:
        return ""
    rule_ids, golden_ids = chosen_ids(
        state, message, language, can_approve=can_approve, days_away=days_away
    )
    parts = [FRAME]
    used = len(FRAME)
    for section_id in rule_ids:
        item = book.get(section_id)
        if item is None:
            continue
        text = _render(item)
        if used + len(text) > MAX_CHARS:
            continue  # the topic sections come last and are the ones to drop
        parts.append(text)
        used += len(text)
    examples = [book[g] for g in golden_ids if g in book]
    if examples:
        parts.append(
            "GOLDEN CONVERSATIONS (worked examples)\n" + "\n\n".join(_render(e) for e in examples)
        )
    return "\n\n".join(parts)


def section_ids() -> list[str]:
    return list(sections())


def describe(state: str, message: str = "") -> dict[str, Any]:
    rules, golden = chosen_ids(state, message)
    return {"rules": rules, "golden": golden, "chars": len(guidance(state, message))}
