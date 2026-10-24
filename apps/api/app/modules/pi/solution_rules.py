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
    r"|[“\"][^”\"]{30,}[”\"]|\bwrite exactly\b|\bhere'?s exactly\b|\b3\)\s",
    re.IGNORECASE,
)
# No invented claims: percentages, money, promised results.
CLAIMS = re.compile(
    r"\d\s*%|\bper ?cent\b|\bpkr\b|\baed\b|\bcad\b|\brs\.?\s*\d|[$€£]|\d{3,}"
    r"|\bguarantee[sd]?\b|\bwill (?:increase|double|triple|grow|boost|raise|bring|make you|fix)\b"
    r"|\bho jaye ?ga\b|\bho jayegi\b|\bho jayenge\b|\bzaroor barhe\b",
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
# R-VAL-05 / R-BUILD-01: named products are vendors even when no "install an app" is said. Case
# matters only for the few that are also ordinary words (a "tally", a "notion", "slack").
PRODUCT_NAMES = (
    r"shopify|canva|zoho|odoo|quick ?books|xero|freshbooks|vyapar|calendly|airtable|trello|asana|clickup"
    r"|hubspot|salesforce|mailchimp|zapier|wix|wordpress|woocommerce|squarespace|paypal|stripe|bitrix24?"
    r"|zendesk|freshdesk|jira|monday\.com|excel|google (?:sheets?|forms?|docs?|keep)"
    r"|microsoft (?:excel|teams|office|word)|whatsapp business(?: api| app)?|power ?bi|google data studio"
    r"|looker studio|tableau|(?-i:Notion|Slack|SAP|Marg)"
    r"|tally ?(?:erp|prime)|(?:use|using|in|on|with|via|from|try) (?-i:Tally)"
)
NAMED_PRODUCT = re.compile(r"\b(?:" + PRODUCT_NAMES + r")\b", re.IGNORECASE)
RECOMMENDS = re.compile(
    r"\b(?:use|using|try|switch(?:ing)? to|move to|go with|install|download|buy|get|sign up|subscribe|"
    r"recommend|best|better|prefer|set up|setup|start with|karein|istemal)\b",
    re.IGNORECASE,
)
# "you use it", "in use", "already using": saying what they have is not recommending it
HAS_IT = re.compile(
    r"\b(?:(?:you|we|they|i|aap|hum)(?:'re| are| both| all)? (?:\w+ )?(?:use|using|used)|in use|"
    r"already using|are using|is used)\b",
    re.IGNORECASE,
)
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n+")


def _product_name(found: str) -> str:
    return re.sub(r"^(?:use|using|in|on|with|via|from|try) ", "", found.lower()).strip()


def named_products(text: str, said: str = "") -> list[str]:
    """Product names in `text` (RV-05). A name the customer used first may be acknowledged but not
    recommended: it is allowed unless its own sentence also says use, try, install, best..."""
    heard = " ".join((said or "").lower().split())
    out: list[str] = []
    for sentence in SENTENCE_BREAK.split(text or ""):
        if sentence.rstrip().endswith(("?", "؟")):
            continue  # asking what they use today is not recommending a product
        for match in NAMED_PRODUCT.finditer(sentence):
            name = _product_name(match.group(0))
            first = name.split()[0] if name else name
            said_it = bool(
                re.search(r"\b" + re.escape(name.rstrip("s")) + r"s?\b", heard)
                or (len(name.split()) > 1 and re.search(r"\b" + re.escape(first) + r"\b", heard))
            )
            around = HAS_IT.sub(" ", sentence.replace(match.group(0), " "))
            if name not in out and not (said_it and not RECOMMENDS.search(around)):
                out.append(name)
    return out


# Emergency numbers are never a "claim" (R-VAL-07: safety is given in full, whatever the budget).
EMERGENCY_NUMBER = re.compile(
    r"(?<![\d-])(?:"
    + "|".join(
        sorted(
            {n for row in safety.NUMBERS.values() for n in row.values()},
            key=len,
            reverse=True,
        )
    )
    + r")(?![\d-])"
)
SAFETY_REFERRAL = re.compile(
    r"\b(?:emergency|ambulance|police|rescue|fire brigade|vet(?:erinar\w+)?|doctor|hospital|"
    r"poison|crisis|helpline)\b",
    re.IGNORECASE,
)
REFER_TO = re.compile(
    r"\b(?:talk|speak|go|call|see|contact|take (?:\w+ ){0,3}to) (?:to )?(?:your |a |the )?"
    r"(?:vet|doctor|hospital|emergency|police|ambulance)\b",
    re.IGNORECASE,
)


def has_safety_referral(text: str) -> bool:
    """A referral to emergency services, a doctor or a vet: given in full, outside the budget."""
    one = text or ""
    return bool(EMERGENCY_NUMBER.search(one) and SAFETY_REFERRAL.search(one)) or bool(
        REFER_TO.search(one)
    )


CLAIM_FIGURES = re.compile(
    r"\d\s*%|\bper ?cent\b|\bpkr\b|\baed\b|\bcad\b|\brs\.?\s*\d|[$€£]|\d{3,}", re.IGNORECASE
)


def claim_hits(text: str, said: str = "", figures_only: bool = False) -> bool:
    """CLAIMS, ignoring emergency numbers and figures the customer gave themselves. With
    `figures_only` only amounts, percentages and 3+ digit figures count: the linter's own promise
    check (R-PROM-01) already judges words like "guaranteed", with the person's usage in mind."""
    body = EMERGENCY_NUMBER.sub(" ", text or "")
    heard = " ".join((said or "").lower().split())
    for figure in set(re.findall(r"\d[\d,.]*\d|\d", said or "")):
        body = re.sub(r"(?<!\d)" + re.escape(figure) + r"(?!\d)", " ", body)
    if figures_only:
        return bool(CLAIM_FIGURES.search(body))
    # a claim word they used themselves ("guaranteed count") may be echoed, never asserted
    body = CLAIMS.sub(
        lambda m: (
            " "
            if re.search(r"[a-z]", m.group(0), re.IGNORECASE) and m.group(0).lower() in heard
            else m.group(0)
        ),
        body,
    )
    return bool(CLAIMS.search(body))


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


REFERRAL_WORDS = re.compile(
    r"\b(?:emergency|police|ambulance|poison (?:centre|center|control)|fire brigade|"
    r"qualified (?:lab|professional|engineer|vet|doctor|electrician)|licensed (?:professional|engineer)|"
    r"talk to (?:the|a) (?:authority|regulator|vet|doctor|lawyer|accountant|scholar))\b",
    re.IGNORECASE,
)


def is_safety_referral(text: str) -> bool:
    """An idea that points the person to emergency services or a qualified professional (R-VAL-07:
    safety is never held back, whatever the budget). Named emergency numbers count too."""
    said = text or ""
    if REFERRAL_WORDS.search(said):
        return True
    numbers = {n for country in safety.NUMBERS.values() for n in _numbers_of(country)}
    return any(re.search(rf"(?<!\d){re.escape(n)}(?!\d)", said) for n in numbers if len(n) >= 2)


def _numbers_of(value: object) -> list[str]:
    if isinstance(value, dict):
        return [n for v in value.values() for n in _numbers_of(v)]
    if isinstance(value, (list, tuple, set)):
        return [n for v in value for n in _numbers_of(v)]
    return re.findall(r"\d{2,4}", str(value))


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
    # R-VAL-07: safety is never held back, so a safety referral (emergency numbers, "call the
    # police", "a qualified lab") may run a sentence or two longer and carry its numbers.
    referral = is_safety_referral(one)
    limit = value_line.IDEA_MAX_WORDS + value_line.IDEA_WORD_SLACK + (25 if referral else 0)
    if len(one.split()) > limit:
        out.reject.append(f"longer than one line: over {limit} words (R-VAL-03)")
    if "?" in one or "؟" in one:
        out.reject.append(
            "a question inside an idea (R-ASK: the one question is pi's last sentence)"
        )
    if not referral and len(re.findall(r"[.!]" + chr(92) + "s+" + chr(92) + "S", one)) > 0:
        out.reject.append("more than one sentence (R-VAL-03)")
    if solutions.banned_tool_words(one, said):
        out.reject.append("tool words or a build named for free (R-BUILD-01)")
    if HOWTO.search(one):  # an idea never asks, so every marker counts (the idea check is strict)
        out.reject.append("how-to, steps, settings or wording to copy (R-VAL-04, R-VAL-05)")
    if (CLAIMS.search(one) or re.search(chr(92) + "d", one)) and not referral:
        # any figure is an invented claim in a free idea; the seeds carry none
        out.reject.append("a number, percentage, amount or promised result (no invented claims)")
    if VENDOR.search(one) or learning.PERSON_OR_COMPETITOR.search(one) or named_products(one, said):
        out.reject.append("names a vendor, an app to buy, a product or a competitor")
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
    if re.search(r"\bwill\b|\bho jaye ?ga\b|\bho jayegi\b|\bho jayenge\b", one, re.IGNORECASE):
        why.append('"will", not "would": no promised results (R-BUILD-06)')
    if CLAIMS.search(one) or VENDOR.search(one) or named_products(one, said):
        why.append("a claim, an amount, a vendor or a named product")
    return why


# A list number starts the reply, a line, or a sentence ("... hai. 2 Aaj ..."); "number 3 says" and
# "3 shops" in the middle of a sentence are not list numbers.
NUMBERED = re.compile(r"(?:^|\n\s*|(?<=[.:;!?؟۔])\s+)(?:[1-9][.)]?)\s+(?=[A-Za-z“\"'])")

# Ideas told in prose: "First..., second..., third", "Pehle..., doosra..., teesra", "one way ...
# another way ... a third". Each family below is one position in the list.
PROSE_POSITIONS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\bfirst(?:ly)?\b|\bpehl[aei]\b|\bone (?:way|idea|option)\b|\bek (?:tareeqa|tareeka|tarika|idea)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?<!\ba )(?<!\bper )(?<!\bone )(?<!\bevery )\bsecond(?:ly)?\b(?! of| ago| later)"
        r"|\bd[ou]{1,2}sr[aei]\b|\banother (?:way|idea|option)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bthird(?:ly)?\b|\bt[ei]{1,2}sr[aei]\b|\bteesr[aei]\b", re.IGNORECASE),
    re.compile(r"\bfourth(?:ly)?\b|\bchauth[aei]\b", re.IGNORECASE),
    re.compile(r"\bfifth(?:ly)?\b|\bpanchw[aei]n?\b", re.IGNORECASE),
)


def prose_ideas(text: str) -> int:
    """Ideas told in prose by position. One marker alone ("First, tell me...") is not a list."""
    present = sum(1 for pattern in PROSE_POSITIONS if pattern.search(text or ""))
    return present if present >= 2 else 0


def count_ideas(text: str, bullets: bool = True) -> int:
    """How many ideas a reply holds, bulleted, numbered or told in prose by position (R-VAL-01
    checks it is at most two). `bullets=False` leaves out dash and dot lists, which a sorted summary
    uses for problems, not ideas."""
    marked = (
        sum(1 for line in (text or "").splitlines() if line.lstrip().startswith(("•", "- ", "* ")))
        if bullets
        else 0
    )
    return max(marked, len(NUMBERED.findall(text or "")), prose_ideas(text))


ORDINALS = ("First", "Second")


def idea_lines(ideas: list[str]) -> str:
    """Ideas as plain sentences, one per line, in prose by position ("First, ... Second, ..."),
    never dots or numbers: they read as a person talking. Counted by `prose_ideas`."""
    clean = [" ".join(str(i).split()).rstrip(". ") + "." for i in ideas if str(i).strip()][:2]
    if len(clean) == 1:
        return clean[0]
    return "\n".join(f"{ORDINALS[n]}, {i[:1].lower()}{i[1:]}" for n, i in enumerate(clean))


def idea_items(text: str) -> list[str]:
    """The listed ideas of a reply, one string each (the first sentence of an inline numbered one)."""
    items = []
    for line in (text or "").splitlines():
        found = re.match(r"\s*(?:[•*-]|\d{1,2}[.)]?)\s+(.*)", line)
        if found:
            items.append(found.group(1))
    if not items and len(NUMBERED.findall(text or "")) >= 2:
        items = [SENTENCE_BREAK.split(part.strip())[0] for part in NUMBERED.split(text)[1:]]
    return items


SUGGESTION = re.compile(
    r"\b(?:you could|you can|try|one way|an idea|one idea|start by|give every|send every|keep a|"
    r"ek tareeqa|ek idea|aap .{0,30}(?:kar sakte|kar saktay)|har .{0,20} (?:mein|me) .{0,20}daal)\b",
    re.IGNORECASE,
)
IDEA_LONG = value_line.IDEA_MAX_WORDS + value_line.IDEA_WORD_SLACK


def long_idea(text: str, carries_ideas: bool) -> str | None:
    """The first idea over about 25 to 30 words (R-VAL-03), or None. A listed item is an idea; so is
    any sentence of a reply that carries ideas, and any suggestion-shaped sentence."""
    for item in idea_items(text):
        if len(item.split()) > IDEA_LONG:
            return item
    for sentence in SENTENCE_BREAK.split(text or ""):
        if len(sentence.split()) > IDEA_LONG and not sentence.rstrip().endswith(("?", "؟")):
            if carries_ideas or SUGGESTION.search(sentence):
                return sentence
    return None


# What pi must never say in an industry (Part 2.2) is written as advice about topics, not as exact
# phrases, so the check takes the noun phrases out of it. Quoted words are lines pi MAY say.
NEVER_LEAD = re.compile(
    r"^(?:anything that (?:helps?|involves?|makes?)|any idea that|ideas? that|that helps?|helps?|"
    r"requests? for|advice on|ask(?:ing)? for|to ask for|comments? on|views? on|"
    r"storing|stores?|how to|helping|any|anything|that|to)\s+",
    re.IGNORECASE,
)
NEGATION = re.compile(
    r"\b(?:never|not|no|don'?t|do not|won'?t|cannot|can'?t|without|nahi|nhi|na)\b|n't",
    re.IGNORECASE,
)


def never_say_fragments(entries: list[str]) -> list[str]:
    """Specific two-to-five word phrases from the never-say prose of an industry."""
    out: list[str] = []
    for entry in entries:
        plain = re.sub(r"[“\"][^”\"]*[”\"]", " ", str(entry))
        for sentence in re.split(r"(?<=[.;])\s+", plain):
            for part in re.split(r",| or | and |;|:", sentence):
                phrase = " ".join(NEVER_LEAD.sub("", part.strip().strip(".")).lower().split())
                phrase = NEVER_LEAD.sub("", phrase)
                if 2 <= len(phrase.split()) <= 5 and len(phrase) >= 9 and phrase not in out:
                    out.append(phrase)
    return out


def never_say_hit(reply: str, entries: list[str]) -> str | None:
    """The industry never-say phrase a reply breaks, or None. A sentence that refuses ("I can't
    advise on how to reduce tax") does not break it."""
    fragments = never_say_fragments(entries)
    for sentence in SENTENCE_BREAK.split(reply or ""):
        lowered = " ".join(sentence.lower().split())
        for phrase in fragments:
            if re.search(r"\b" + re.escape(phrase) + r"\b", lowered) and not NEGATION.search(
                lowered
            ):
                return phrase
    return None


SHEET_WORDS = re.compile(r"\b(?:excel|spreadsheets?|sheets?|google sheets?)\b", re.IGNORECASE)


def howto_hits(text: str, said: str = "") -> list[str]:
    """How-to markers in `text`. A single tool or layout word the person used first, or one that
    pi only asks about ("which columns do you keep?"), is not giving the how; steps, "pehle... phir",
    quoted wording to send and "copy this" always are."""
    heard = (said or "").lower()
    family = bool(SHEET_WORDS.search(heard))  # they named a sheet, so "spreadsheet" echoes it
    hits: list[str] = []
    for sentence in SENTENCE_BREAK.split(text or ""):
        asking = sentence.rstrip().endswith(("?", "؟"))
        for match in HOWTO.finditer(sentence):
            word = match.group(0).lower()
            single = " " not in word and not word.startswith(("step", "1"))
            echoed = re.search(r"\b" + re.escape(word), heard) or (
                family and SHEET_WORDS.fullmatch(word)
            )
            if single and (asking or echoed):
                continue
            if word in ("google sheet", "google sheets") and family:
                continue
            hits.append(word)
    return hits


def check_sample_reply(text: str, said: str = "", bullets: bool = True) -> list[str]:
    """Why a sample solution reply may not seed the example bank or replace the current one."""
    why: list[str] = []
    if count_ideas(text, bullets) > value_line.IDEAS_PER_MESSAGE:
        why.append("more than two ideas (R-VAL-01)")
    if howto_hits(text, said):
        why.append("how-to markers (R-VAL-04)")
    if solutions.banned_tool_words(text or "", said):
        why.append("tool words (R-BUILD-01)")
    if named_products(text or "", said):
        why.append("a named product or vendor (R-VAL-05)")
    if len(solutions.AUTOMATIC.findall(text or "")) > 1:
        why.append('"automatically" more than once (R-BUILD-04)')
    if claim_hits(text or "", said) or learning.PERSON_OR_COMPETITOR.search(text or ""):
        why.append("a claim, an amount or a named competitor")
    if has_personal_data(text or ""):
        why.append("personal data (R-PRIV-07)")
    return why
