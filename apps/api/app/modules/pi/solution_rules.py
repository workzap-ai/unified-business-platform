# ruff: noqa: E501  (long regexes read better on one line)
"""What a learned idea, a learned Level 2 line or a sample reply may say (Addendum 2, Part 3.8).

Pure functions, no database and no model. The same checks run on a seed, on an idea an owner
described, on one a reviewer wrote into a document and on one a model drafted, so the free part can
never grow into the paid part by learning: one line, what plus why, no steps or settings, no
vendors, no claims, only catalogue builds. `check_idea` says reject (the text can never be used) or
review (it touches money or a regulated topic, so a person decides, Part 3.5).
"""

import re
from dataclasses import dataclass, field

from app.modules.pi import learning, safety, solutions, value_line
from app.modules.pi.problems import redact as redact_contact

# R-VAL-04, R-VAL-05: no how-to, no systems for free.
HOWTO = re.compile(
    r"\bstep\s*(?:1|one)\b|\bstep[- ]by[- ]step\b|\bpehle\b.{1,60}\bphir\b|\bfirst\b.{1,60}\bthen\b"
    r"|\bsettings?\b|\bformulas?\b|\bcolumns?\b|\btemplates?\b|\bcopy (?:this|the following)\b"
    r"|\bspreadsheet\b|\bgoogle sheets?\b|\bexcel\b|\bclick\b|\bpaste\b|\bscript\b"
    r"|[“\"][^”\"]{30,}[”\"]|\bwrite exactly\b|\bhere'?s exactly\b|\b1\)\s",
    re.IGNORECASE,
)
# No invented claims: percentages, money, promised results.
CLAIMS = re.compile(
    r"\d\s*%|\bper ?cent\b|\bpkr\b|\baed\b|\bcad\b|\brs\.?\s*\d|[$€£]|\d{3,}"
    r"|\bguarantee[sd]?\b|\bwill (?:increase|double|triple|grow|boost|raise|bring|make you|fix)\b"
    r"|\bho jayega\b|\bho jaye ga\b|\bzaroor barhe\b",
    re.IGNORECASE,
)
# No vendors or competitors: nothing to buy, install or sign up for; no named competitor.
VENDOR = re.compile(
    r"\b(?:install|download|subscribe to|sign up (?:for|to)|hire (?:an? )?(?:agency|freelancer|consultant)"
    r"|use (?:an? )?(?:app|software|tool|platform)|which (?:app|software|tool)"
    r"|(?:buy|purchase) (?:an?|the|this|some) (?:app|software|tool|platform|system)"
    r"|try (?:the )?[A-Z][a-z]+ app)\b",
    re.IGNORECASE,
)
# Money or a regulated topic: not rejected, but a person decides (Part 3.5).
REGULATED = re.compile(
    r"\b(?:discount|prices?|pricing|loan|credit|interest|tax|legal|law|lawyer|licen[cs]e|medical|medicine|"
    r"doctor|vet(?:erinary)?|vaccin\w*|dose|dosage|drug|antibiotic|pesticide|spray|fertili[sz]er|aviation|"
    r"safety|insurance|refund|payment|invoice|salary|wages?)\b",
    re.IGNORECASE,
)

KINDS: dict[str, re.Pattern[str]] = {
    "measure": re.compile(
        r"\b(?:code|codes|measure|count|compare|track|tally|note every|log|record|survey|check which|"
        r"pull sales|sales by|find out|ask each)\b",
        re.IGNORECASE,
    ),
    "bring_back": re.compile(
        r"\b(?:past customers|old customers|remind|follow up|win back|repeat|reactivate|lapsed|"
        r"birthday|reorder|message (?:your|the|every)|call (?:your|the|every))\b",
        re.IGNORECASE,
    ),
    "get_found": re.compile(
        r"\b(?:maps|google|profile|listing|photos?|post|reel|instagram|facebook|signboard|visible|"
        r"ad|ads|poster|banner|referral)\b",
        re.IGNORECASE,
    ),
    "fix_process": re.compile(
        r"\b(?:checklist|schedule|roster|label|stock[- ]?take|rotate|fixed time|separate|daily close|"
        r"one person|handover|sign[- ]off)\b",
        re.IGNORECASE,
    ),
}


def has_personal_data(text: str) -> bool:
    """Card, ID, account, email or phone patterns, or a shared contact (R-PRIV-07)."""
    said = text or ""
    return bool(safety.redact_pii(said).kinds) or redact_contact(said)[1]


def redacted(text: str) -> str:
    """The text with every such pattern taken out, for what is stored as evidence."""
    return redact_contact(safety.redact_pii(text or "").text)[0]


def idea_kind(text: str) -> str:
    """The kind of an idea ("get found", "bring back", "measure", "fix the routine"), so that when
    an owner says "already doing that" pi can swap to a different kind (Part 3.3)."""
    for kind, pattern in KINDS.items():
        if pattern.search(text or ""):
            return kind
    return "other"


@dataclass
class Verdict:
    reject: list[str] = field(default_factory=list)
    review: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.reject

    @property
    def needs_review(self) -> bool:
        return not self.reject and bool(self.review)


def check_idea(text: str, said: str = "") -> Verdict:
    """Judge one idea (a learned one, or a seed being loaded). One line, what plus why."""
    one = " ".join((text or "").split())
    out = Verdict()
    if not one:
        out.reject.append("empty")
        return out
    if "\n" in (text or "").strip():
        out.reject.append("more than one line (R-VAL-03)")
    limit = value_line.IDEA_MAX_WORDS + value_line.IDEA_WORD_SLACK
    if len(one.split()) > limit:
        out.reject.append(f"longer than one line: over {limit} words (R-VAL-03)")
    if "?" in one or "؟" in one:
        out.reject.append(
            "a question inside an idea (R-ASK: the one question is pi's last sentence)"
        )
    if len(re.findall(r"[.!]" + chr(92) + "s+" + chr(92) + "S", one)) > 0:
        out.reject.append("more than one sentence (R-VAL-03)")
    if solutions.banned_tool_words(one, said):
        out.reject.append("tool words or a build named for free (R-BUILD-01)")
    if HOWTO.search(one):
        out.reject.append("how-to, steps, settings or wording to copy (R-VAL-04, R-VAL-05)")
    if CLAIMS.search(one) or re.search(chr(92) + "d", one):
        # any figure is an invented claim in a free idea; the seeds carry none
        out.reject.append("a number, percentage, amount or promised result (no invented claims)")
    if VENDOR.search(one) or learning.PERSON_OR_COMPETITOR.search(one):
        out.reject.append("names a vendor, an app to buy or a competitor")
    if learning.SOCIAL_PROOF.search(one):
        out.reject.append("social proof (R-SELL-03)")
    if learning.INJECTION.search(one) or learning.VALUE_LINE_ATTEMPT.search(one):
        out.reject.append("tries to give pi instructions or change the value line")
    if has_personal_data(one):
        out.reject.append("personal data (R-PRIV-07)")
    if REGULATED.search(one) or safety.advice_asked(one) is not None:
        out.review.append("money or a regulated topic: a person decides")
    return out


def check_build_line(text: str, keys: list[str], said: str = "") -> list[str]:
    """Why a learned Level 2 line (what Workzap would build) is rejected; empty when it is fine."""
    one = " ".join((text or "").split())
    why: list[str] = []
    if not keys:
        why.append("names no build")
    for key in keys:
        if key not in solutions.CATALOGUE:
            why.append(f"build {key!r} is not in the catalogue")
    if len(keys) > 2:
        why.append("more than two builds in one line (R-BUILD-05)")
    if solutions.banned_tool_words(one, said):
        why.append("tool words (R-BUILD-01)")
    if re.search(r"\bwill\b|\bho jayega\b|\bho jaye ga\b", one, re.IGNORECASE):
        why.append('"will", not "would": no promised results (R-BUILD-06)')
    if CLAIMS.search(one) or VENDOR.search(one):
        why.append("a claim, an amount or a vendor")
    return why


NUMBERED = re.compile(r"(?:^|\n|\s)(?:[1-9][.)]?)\s+(?=[A-Za-z“\"'])")


def count_ideas(text: str) -> int:
    """How many numbered or bulleted ideas a reply holds (R-VAL-01 checks it is at most two)."""
    bullets = sum(
        1 for line in (text or "").splitlines() if line.lstrip().startswith(("•", "- ", "* "))
    )
    return max(bullets, len(NUMBERED.findall(text or "")))


def check_sample_reply(text: str, said: str = "") -> list[str]:
    """Why a sample solution reply may not seed the example bank or replace the current one."""
    why: list[str] = []
    if count_ideas(text) > value_line.IDEAS_PER_MESSAGE:
        why.append("more than two ideas (R-VAL-01)")
    if HOWTO.search(text or ""):
        why.append("how-to markers (R-VAL-04)")
    if solutions.banned_tool_words(text or "", said):
        why.append("tool words (R-BUILD-01)")
    if len(solutions.AUTOMATIC.findall(text or "")) > 1:
        why.append('"automatically" more than once (R-BUILD-04)')
    if CLAIMS.search(text or "") or learning.PERSON_OR_COMPETITOR.search(text or ""):
        why.append("a claim, an amount or a named competitor")
    if has_personal_data(text or ""):
        why.append("personal data (R-PRIV-07)")
    return why
