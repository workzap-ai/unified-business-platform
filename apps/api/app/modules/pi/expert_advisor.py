# ruff: noqa: E501
"""The expert advisor: pi's ideas written like a senior operator-consultant would (solution_source "expert").

Only when `response_rules.brain.solution_source` is "expert"; every other workspace keeps the pack
entries and the single free-ideas call. Three stages, none of which may raise (the caller falls
back to the earlier behaviour on None):

1. DIAGNOSE + PROPOSE (one structured call, a persona for the owner's industry, sub-type and
   country, told today's date and that practices must be current): the problem in the owner's own
   words, up to three likely causes ranked with evidence taken only from the owner's words, the one
   missing fact that would change the advice most (a plain question), and five candidate ideas each
   tagged with the cause it addresses, what it assumes the owner has, and the current practice it
   rests on.
2. JUDGE (a cheaper alias, can be switched off with `brain.expert_judge: false`): scores each
   candidate 0-5 on fit to the cause, correct for the industry, current, grounded (assumes nothing
   the owner did not say), specific and safe, and picks the best two.
3. VET (deterministic): the chosen ideas go through the same guards every idea passes (check_idea,
   the idea filter G1-G8, the reply linter's shape, one short plain sentence, no figures or time);
   one that fails is replaced by the next best candidate. Fewer than two survivors: what survived
   plus the missing-fact question; none: the question alone (one question, the last sentence).

The model's text is data: it can never relax a rule, the rules are applied here in code.
"""

import asyncio
import dataclasses
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.ai.manager import LLMManager
from app.ai.types import Message
from app.modules.pi import (
    currency_notes,
    idea_filter,
    solution_free,
    solution_lint,
    solution_rules,
)
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)

SOURCE = "expert"
TOTAL_TIMEOUT = 40.0  # seconds for the whole pipeline; past it pi falls back to its earlier way
CANDIDATES = 5
MAX_CAUSES = 3
PER_PROBLEM = 2  # Book 5 decision 5: two ideas per problem, up to eight per business
PURPOSE_DIAGNOSE = "pi_expert_diag"
PURPOSE_JUDGE = "pi_expert_judge"
JUDGE_ALIAS = "fast"
PASS_MARK = 3  # a candidate scored below this on any quality is dropped
SAFE_MARK = 4

PERSONA = """You are a senior operator-consultant: twenty years running and advising {industry} businesses in {country}, now
helping the owner of one on WhatsApp through pi, an AI assistant. You know how this trade really works today
(today is {today}): what customers expect, where money and time leak, which practices are current in 2026 and which
are outdated. You never give advice a licence is needed for (medical, veterinary, legal, tax, financial)."""

DIAGNOSE_RULES = """Think like that operator, then answer with ONE JSON object and nothing else:
{
 "problem": "the owner's problem restated in their own words, one sentence",
 "causes": [ {"cause": "a likely cause, 3 to 10 words", "evidence_for": ["owner's words that support it"], "evidence_against": ["owner's words that weaken it"]} ],
 "missing_fact": "the single fact that would most change your advice",
 "question": "that fact as ONE plain English question to the owner, one sentence, about the main problem or its causes only",
 "ideas": [ {"idea": "...", "addresses": "the cause it works on", "assumes": ["what the owner must already have"], "current_practice": "the 2026 practice it rests on, a few words"} ]
}
Rules:
- Write every field, the question and the ideas in plain ENGLISH whatever language the owner writes in (pi
  translates for the owner afterwards and checks the English).
- causes: at most 3, ranked most likely first. evidence_for and evidence_against come ONLY from what the owner
  said (quote or near-quote); an empty list is better than a guess. Never invent a fact about the business.
- question: about THE PROBLEM THE OWNER RAISED and its causes. Never about another process (who follows up,
  what staff do, what the CRM is) unless the owner linked it to the problem. No mention of solutions, documents,
  quotes or prices. It ends with a question mark.
- ideas: exactly 5, each different in kind and each aimed at one of the causes (cover the top two causes).
  Each idea:
  * is ONE sentence of 12 to 24 words: what the OWNER does, a comma, then "so" and the benefit in the owner's terms;
  * can be done by the owner or staff with what the owner said they have (a notebook, a phone, staff, the
    showroom, the records they named). Nothing to buy, install, subscribe to or set up;
  * assumes ONLY what the owner said. Never assume videos, a page, a website, ads, a customer list, a chat group
    or any asset or channel the owner did not name. An idea may tell the owner to ASK customers or staff
    something, LOOK at what a customer sees in the place they named (shop front, counter, queue), COUNT or NOTE
    something from records they named, or change how something they named is done. Never assume an online
    listing, a search result, a page or a map entry exists; never assume a record, size chart, register,
    notebook, past bookings or staff role they did not mention (ask or note instead);
  * is correct for {industry} today and current for 2026: not a practice that has been outdated by how customers
    now find, compare and decide; say it by kind, never by app, brand or product name;
  * is specific to THIS problem and uses the owner's own nouns; an idea that would fit any business is wrong;
  * has no digits, no percentage, no amount, no time or duration (no "this week", "daily", "a month"), no steps
    and no wording to copy, no jargon (bottleneck, workflow, streamline, optimise, leverage, touchpoint, KPI);
  * never tells the owner how to set a price, rate, discount, credit limit or payment term (those need a person), and
    the benefit after "so" says what the owner will SEE or KNOW, never an outcome (no "never", "always", "cannot",
    "stops", "pulls buyers");
  * assumes no equipment, machine, scale, vehicle, phone or record the owner did not name;
  * never tells the owner to START something they already said they do (they keep a register: do not ask them
    to keep a notebook; find what is wrong with how the register is kept and change that);
  * never says what Workzap, pi or "we" would do, asks no question, and never gives medical, legal, tax or
    financial advice;
  * never contains anything in never_say_list.
- examples_of_level (when given) show the LEVEL of an idea, from similar businesses; do not copy them and do not
  borrow the channel or asset they assume.
- Do not repeat or reword anything in pi_already_said_do_not_repeat_or_reword.
- If the owner has not said enough to find the cause, say so in missing_fact and still give 5 ideas that are useful
  whatever the cause is."""

JUDGE_RULES = """You are a strict reviewer for pi, a WhatsApp business assistant. Below are the owner's own words, the likely causes and
candidate ideas. Score EACH candidate 0 to 5 on:
- fits: it works on the most likely cause (5) or only a remote one (0)
- correct: right for this industry as it really works (0 = wrong or misleading, or tells the owner to start something they said they already do)
- current: how a good operator does it in 2026 (0 = outdated practice)
- grounded: assumes nothing the owner did not say: no video, page, ads, list, tool, staff or asset they never mentioned (0 = invents things)
- specific: tied to THIS problem, not generic advice that fits any business (0 = generic)
- safe: no medical, veterinary, legal, tax or financial advice, no promised result, no advice on how to set a price, rate, discount or payment term (0 = unsafe)
Then choose the best two candidates (different in kind) with a one-line reason each.
Answer with ONE JSON object only:
{"scores": [{"i": 0, "fits": 0, "correct": 0, "current": 0, "grounded": 0, "specific": 0, "safe": 0}],
 "best": [{"i": 0, "reason": "..."}, {"i": 1, "reason": "..."}]}"""

# What the brain prompt adds when a diagnosis is known (the next question targets the main problem).
PROMPT_RULE = """
- main_problem and main_problem_causes (when present) are the owner's MAIN problem and the causes pi
  thinks are likely. Your one question this turn is about that problem or one of those causes, never
  about an adjacent process (who follows up, what staff do, which system) the owner did not link to it.
  When suggested_next_question is present, ask it (in your own words, in the owner's language) unless the
  owner's last message already answers it.
"""

QUALITIES = ("fits", "correct", "current", "grounded", "specific", "safe")
JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
SOLUTION_WORDS = re.compile(
    r"\b(?:solutions?|documents?|quotes?|quotation|prices?|pricing|offers?|proposal|invoice|pay(?:ment)?|"
    r"workzap|build|app|software|system|crm)\b",
    re.IGNORECASE,
)
QUESTION_MARKS = ("?", "؟")
OUTCOME_CLAIM = re.compile(
    r"\bso\b[^.]*\b(?:never|always|cannot|can't|guarantee\w*|pulls? (?:buyers|customers|guests)|stops? for good)\b",
    re.IGNORECASE,
)
MAX_QUESTION_WORDS = 30
# A channel or asset a pack idea may assume: kept out of the examples unless the owner named it.
CHANNEL = re.compile(
    r"\b(?:videos?|reels?|shorts|clips?|captions?|pin(?:ned)?|pages?|posts?|stories|story|ads?|adverts?|advertis\w*|"
    r"campaigns?|boost\w*|websites?|web ?shop|online|facebook|instagram|tiktok|youtube|google|whatsapp|"
    r"broadcast|newsletter|email|sms|catalogue|catalog|app|software|template|spreadsheet|dashboard|crm)\b",
    re.IGNORECASE,
)


def switched_on(response_rules: dict[str, Any] | None) -> bool:
    """`brain.solution_source == "expert"` in brain mode. Anything else keeps today's behaviour."""
    rules = response_rules or {}
    return (
        rules.get("pi_mode") == "brain"
        and (rules.get("brain") or {}).get("solution_source") == SOURCE
    )


def judge_on(response_rules: dict[str, Any] | None) -> bool:
    return ((response_rules or {}).get("brain") or {}).get("expert_judge", True) is not False


@dataclass
class Cause:
    cause: str
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)


@dataclass
class Candidate:
    idea: str
    addresses: str = ""
    assumes: list[str] = field(default_factory=list)
    current_practice: str = ""
    scores: dict[str, int] = field(default_factory=dict)
    picked: bool = False

    def total(self) -> int:
        return sum(self.scores.get(q, 0) for q in QUALITIES)

    def passes_judge(self) -> bool:
        if not self.scores:
            return True  # not judged (judge off or the judge answered nothing usable)
        return all(self.scores.get(q, 0) >= PASS_MARK for q in QUALITIES if q != "safe") and (
            self.scores.get("safe", 0) >= SAFE_MARK
        )


@dataclass
class Diagnosis:
    problem: str = ""
    causes: list[Cause] = field(default_factory=list)
    missing_fact: str = ""
    question: str = ""
    candidates: list[Candidate] = field(default_factory=list)


@dataclass
class Advice:
    """What the pipeline hands back. `ideas` may be empty; `question` is the missing-fact question
    (vetted, one sentence, ends with a question mark) or "" when none is usable."""

    ideas: list[str] = field(default_factory=list)
    question: str = ""
    causes: list[str] = field(default_factory=list)
    problem: str = ""
    judged: bool = False
    dropped: int = 0  # candidates the vetting removed
    drops: list[str] = field(default_factory=list)  # why, for the evaluation (never shown)


# --- parsing (tolerant: a model that adds a fence or a sentence around the JSON still counts) ----


def load_json(text: str) -> dict[str, Any] | None:
    stripped = FENCE.sub("", (text or "").strip())
    found = JSON_OBJECT.search(stripped)
    for chunk in (stripped, found.group(0) if found else ""):
        if not chunk:
            continue
        try:
            data = json.loads(chunk)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict):
            return data
    return None


def _strings(value: Any, limit: int, size: int = 200) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip()[:size] for v in value if str(v).strip()][:limit]


def _items(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    return value if isinstance(value, list) else []


def parse_diagnosis(text: str) -> Diagnosis | None:
    data = load_json(text)
    if data is None:
        return None
    causes = [
        Cause(
            cause=str(c.get("cause") or "").strip()[:120],
            evidence_for=_strings(c.get("evidence_for"), 3),
            evidence_against=_strings(c.get("evidence_against"), 3),
        )
        for c in _items(data, "causes")
        if isinstance(c, dict) and str(c.get("cause") or "").strip()
    ][:MAX_CAUSES]
    candidates: list[Candidate] = []
    for item in _items(data, "ideas"):
        if isinstance(item, str):
            item = {"idea": item}
        if not isinstance(item, dict) or not str(item.get("idea") or "").strip():
            continue
        candidates.append(
            Candidate(
                idea=" ".join(str(item["idea"]).split()),
                addresses=str(item.get("addresses") or "").strip()[:120],
                assumes=_strings(item.get("assumes"), 5, 80),
                current_practice=str(item.get("current_practice") or "").strip()[:160],
            )
        )
    diagnosis = Diagnosis(
        problem=str(data.get("problem") or "").strip()[:300],
        causes=causes,
        missing_fact=str(data.get("missing_fact") or "").strip()[:300],
        question=" ".join(str(data.get("question") or "").split())[:300],
        candidates=candidates[: CANDIDATES + 2],
    )
    if not (diagnosis.candidates or diagnosis.question or diagnosis.causes):
        return None
    return diagnosis


def _score(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, min(5, int(round(value))))


def apply_judgement(candidates: list[Candidate], text: str) -> bool:
    """Put the judge's scores on the candidates and mark its picks. False when the answer is
    unusable (the candidates are then used in the order proposed)."""
    data = load_json(text)
    if data is None or not isinstance(data.get("scores"), list):
        return False
    rows = data["scores"]
    scored = 0
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("i"), int):
            continue
        n = row["i"]
        if not 0 <= n < len(candidates):
            continue
        marks = {q: s for q in QUALITIES if (s := _score(row.get(q))) is not None}
        if len(marks) == len(QUALITIES):
            candidates[n].scores = marks
            scored += 1
    if not scored:
        return False
    for pick in _items(data, "best"):
        n = pick.get("i") if isinstance(pick, dict) else None
        if isinstance(n, int) and 0 <= n < len(candidates):
            candidates[n].picked = True
    return True


def ranked(candidates: list[Candidate]) -> list[Candidate]:
    """The candidates worth vetting, best first: the judge's picks, then by total score. A candidate
    the judge scored below the mark on a quality is out. Unjudged candidates keep their order."""
    usable = [c for c in candidates if c.passes_judge()]
    if not any(c.scores for c in usable):
        return usable
    return sorted(usable, key=lambda c: (not c.picked, -c.total()))


# --- stage 3: the deterministic vetting ---------------------------------------------------------


def question_ok(question: str) -> bool:
    """One short plain sentence that ends in a question mark and carries no solution word."""
    q = " ".join((question or "").split())
    if not q or not q.endswith(QUESTION_MARKS) or q.count("?") + q.count("؟") != 1:
        return False
    if len(q.split()) > MAX_QUESTION_WORDS or SOLUTION_WORDS.search(q):
        return False
    if re.search(r"\d{3,}", q):
        return False
    return len(re.findall(r"[.!]\s", q)) == 0  # one sentence


def why_dropped(
    idea: str,
    owner_words: str,
    never_say: list[str],
    facts: set[str],
    ctx: idea_filter.IdeaContext | None,
) -> str:
    """The first guard an idea fails, for the evaluation log (same order as solution_free.vetted)."""
    verdict = solution_rules.check_idea(idea, owner_words)
    if verdict.reject:
        return "check_idea:reject " + ",".join(str(x) for x in verdict.reject)[:60]
    if verdict.review and not solution_free.only_price_talk(idea):
        return "check_idea:review " + ",".join(str(x) for x in verdict.review)[:60]
    if never_say and solution_rules.never_say_hit(idea, never_say):
        return "never_say"
    if broke := idea_filter.failures(idea, owner_words, ctx):
        return "filter:" + ",".join(broke)
    if solution_free.GENERIC.search(idea) or not solution_free.uses_a_fact(idea, facts):
        return "generic_or_no_fact"
    if len(idea.split()) > solution_free.MAX_WORDS or solution_free.JARGON.search(idea):
        return "too_long_or_jargon"
    return "timeline_or_other"


def vet(
    ordered: list[Candidate],
    *,
    owner_words: str,
    never_say: list[str],
    facts: set[str],
    ctx: idea_filter.IdeaContext | None,
    want: int,
    report: dict[str, Any] | None = None,
    trace: list[str] | None = None,
) -> list[str]:
    """The first `want` candidates, in order, that pass every guard (one at a time, so a failure is
    replaced by the next best)."""
    chosen: list[str] = []
    if ctx is not None and ctx.nodes:
        # G8 judges an idea against the map by shared words. These candidates were written for the
        # owner's own main problem, and "salesman" against "sales team" is no reason to drop a good
        # one, so the map check is left to the diagnosis (seen on a real model, 2026-10-27).
        ctx = dataclasses.replace(ctx, nodes=(), node_categories=())
    for candidate in ordered:
        if len(chosen) >= want:
            break
        text = candidate.idea
        if "?" in text or "؟" in text:
            continue
        one = solution_free.vetted([text], owner_words, never_say, facts, ctx, report)
        if not one:
            if trace is not None:
                trace.append(
                    f"{why_dropped(text, owner_words, never_say, facts, ctx)}: {text[:110]}"
                )
            continue
        idea = one[0]
        if not solution_lint.passes(idea):
            continue
        if OUTCOME_CLAIM.search(idea):  # "so X never happens" is a promised result
            if trace is not None:
                trace.append(f"outcome_claim: {idea[:110]}")
            continue
        if idea_filter.repeats(idea, chosen):  # two near-identical ideas are one idea
            continue
        chosen.append(idea)
    return chosen


def pack_examples(entry_ideas: list[str], owner_words: str, count: int = 3) -> list[str]:
    """Pack ideas as examples of level: those that assume no channel or asset the owner never named."""
    out: list[str] = []
    named = owner_words.lower()
    for idea in entry_ideas:
        if idea_filter.invented_context(idea, owner_words):
            continue
        if any(m.group(0).lower() not in named for m in CHANNEL.finditer(idea)):
            continue
        out.append(idea[:240])
        if len(out) == count:
            break
    return out


# --- the model calls -----------------------------------------------------------------------------


def _text(response: Any) -> str:
    return str(getattr(response, "text", "") or "")


async def diagnose(
    manager: LLMManager,
    scope: WorkspaceScope,
    *,
    alias: str,
    conversation_id: UUID | None,
    owner_said: list[str],
    problems: list[str],
    industry: str | None,
    subtype: str,
    country: str,
    never_say: list[str],
    already_said: list[str],
    examples: list[str],
    today: str,
) -> Diagnosis | None:
    kind = industry or "small"
    system = (
        PERSONA.format(industry=kind, country=country or "Pakistan, the UAE or Canada", today=today)
        + "\n\n"
        + DIAGNOSE_RULES.replace("{industry}", kind)
    )
    user = json.dumps(
        {
            "today": today,
            "industry": industry or "not known yet",
            "problem_sub_type": subtype or "not known",
            "country": country or "not known",
            "problems_noted": [p[:120] for p in problems[-4:]],
            "owner_first_message": (owner_said[:1] or [""])[0][:600],
            "owner_messages_in_order": [m[:500] for m in owner_said[-8:]],
            "never_say_list": never_say[:8],
            "pi_already_said_do_not_repeat_or_reword": already_said[-8:],
            "examples_of_level_not_to_copy": examples[:3],
            "sector_briefing_2026_may_help_never_assume": currency_notes.prompt_block(
                industry or ""
            ),
        },
        ensure_ascii=False,
    )
    try:
        response = await manager.complete(
            scope,
            alias=alias,
            purpose=PURPOSE_DIAGNOSE,
            messages=[Message.system(system), Message.user(user)],
            max_tokens=4000,
            temperature=0.4,
            conversation_id=conversation_id,
        )
    except Exception:  # noqa: BLE001 - the caller falls back
        logger.warning("pi_expert_diagnose_failed", exc_info=True)
        return None
    return parse_diagnosis(_text(response))


async def judge(
    manager: LLMManager,
    scope: WorkspaceScope,
    *,
    conversation_id: UUID | None,
    owner_said: list[str],
    diagnosis: Diagnosis,
    industry: str | None,
) -> bool:
    user = json.dumps(
        {
            "industry": industry or "not known yet",
            "owner_messages_in_order": [m[:500] for m in owner_said[-8:]],
            "likely_causes": [c.cause for c in diagnosis.causes],
            "sector_briefing_2026": currency_notes.prompt_block(industry or ""),
            "candidates": [
                {
                    "i": n,
                    "idea": c.idea,
                    "addresses": c.addresses,
                    "assumes": c.assumes,
                    "current_practice": c.current_practice,
                }
                for n, c in enumerate(diagnosis.candidates)
            ],
        },
        ensure_ascii=False,
    )
    try:
        response = await manager.complete(
            scope,
            alias=JUDGE_ALIAS,
            purpose=PURPOSE_JUDGE,
            messages=[Message.system(JUDGE_RULES), Message.user(user)],
            max_tokens=1500,
            temperature=0.0,
            conversation_id=conversation_id,
        )
    except Exception:  # noqa: BLE001 - unjudged candidates are still vetted
        logger.warning("pi_expert_judge_failed", exc_info=True)
        return False
    return apply_judgement(diagnosis.candidates, _text(response))


async def _pipeline(
    manager: LLMManager,
    scope: WorkspaceScope,
    *,
    alias: str,
    conversation_id: UUID | None,
    owner_said: list[str],
    problems: list[str],
    industry: str | None,
    subtype: str,
    country: str,
    never_say: list[str],
    already_said: list[str],
    examples: list[str],
    ctx: idea_filter.IdeaContext | None,
    want: int,
    use_judge: bool,
    today: str,
    ideas_wanted: bool,
) -> Advice | None:
    diagnosis = await diagnose(
        manager,
        scope,
        alias=alias,
        conversation_id=conversation_id,
        owner_said=owner_said,
        problems=problems,
        industry=industry,
        subtype=subtype,
        country=country,
        never_say=never_say,
        already_said=already_said,
        examples=examples,
        today=today,
    )
    if diagnosis is None:
        return None
    question = diagnosis.question if question_ok(diagnosis.question) else ""
    advice = Advice(
        question=question,
        causes=[c.cause for c in diagnosis.causes],
        problem=diagnosis.problem,
    )
    if not ideas_wanted or want <= 0 or not diagnosis.candidates:
        return advice
    if use_judge and len(diagnosis.candidates) > 1:
        advice.judged = await judge(
            manager,
            scope,
            conversation_id=conversation_id,
            owner_said=owner_said,
            diagnosis=diagnosis,
            industry=industry,
        )
    owner_words = " ".join([*owner_said, *problems])
    # the 'uses a word the owner said' check compares English with the owner's own language and
    # wrongly dropped every idea for a Roman Urdu petrol-pump owner; the judge scores groundedness
    facts: set[str] = set()
    report: dict[str, Any] = {}
    order = ranked(diagnosis.candidates)
    advice.ideas = vet(
        order,
        owner_words=owner_words,
        never_say=never_say,
        facts=facts,
        ctx=ctx,
        want=want,
        report=report,
        trace=advice.drops,
    )
    advice.dropped = len(diagnosis.candidates) - len(advice.ideas)
    return advice


async def advise(
    manager: LLMManager,
    scope: WorkspaceScope,
    *,
    alias: str,
    conversation_id: UUID | None,
    owner_said: list[str],
    problems: list[str] | None = None,
    industry: str | None = None,
    subtype: str = "",
    country: str = "",
    never_say: list[str] | None = None,
    already_said: list[str] | None = None,
    entry_ideas: list[str] | None = None,
    idea_ctx: idea_filter.IdeaContext | None = None,
    want: int = 2,
    use_judge: bool = True,
    ideas_wanted: bool = True,
    today: str | None = None,
    time_limit: float = TOTAL_TIMEOUT,
) -> Advice | None:
    """The expert's ideas and missing-fact question for what the owner described, or None (the model
    failed, timed out or answered nothing usable): the caller then falls back. Never raises."""
    when = today or datetime.now(UTC).strftime("%d %B %Y")
    owner_words = " ".join([*owner_said, *(problems or [])])
    try:
        async with asyncio.timeout(time_limit):
            return await _pipeline(
                manager,
                scope,
                alias=alias,
                conversation_id=conversation_id,
                owner_said=owner_said,
                problems=problems or [],
                industry=industry,
                subtype=subtype,
                country=country,
                never_say=never_say or [],
                already_said=already_said or [],
                examples=pack_examples(entry_ideas or [], owner_words),
                ctx=idea_ctx,
                want=want,
                use_judge=use_judge,
                today=when,
                ideas_wanted=ideas_wanted,
            )
    except Exception:  # noqa: BLE001 - including the timeout: the caller has a fallback
        logger.warning("pi_expert_advise_failed", exc_info=True)
        return None


# --- the diagnosis cache and the question context -------------------------------------------------

NEED_FACT_PREFIX = "I need one more fact before I can say anything useful here."


def need_fact_reply(question: str) -> str:
    """No idea survived: one missing fact, one question, last. No solution word."""
    return f"{NEED_FACT_PREFIX} {question}"


def main_problem(noted: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The owner's main problem: the one they ranked first, else the most severe, else the latest."""
    items = [p for p in noted or [] if isinstance(p, dict) and p.get("title")]
    if not items:
        return None
    ranks = [p for p in items if isinstance(p.get("rank"), int)]
    if ranks:
        return min(ranks, key=lambda p: p["rank"])
    scored = [p for p in items if isinstance(p.get("score"), (int, float))]
    if scored:
        return max(scored, key=lambda p: (p["score"], items.index(p)))
    return items[-1]


def problem_key(problem: dict[str, Any] | None) -> str:
    """Identifies the problem and what the owner said about it: a new problem or a new fact on it
    changes the key and so refreshes the cached diagnosis."""
    if not problem:
        return ""
    parts = [  # the title, not the short ref: a note made this turn has no ref yet
        str(problem.get("title") or ""),
        str(problem.get("cause") or ""),
        *[str(w) for w in problem.get("user_words") or []],
    ]
    return re.sub(r"\s+", " ", "|".join(parts).lower())[:400]


def remember(
    brief: dict[str, Any], problem: dict[str, Any] | None, advice: Advice
) -> dict[str, Any]:
    """The diagnosis cached on the brief (a copy), so it is not recomputed each turn."""
    if problem is None or not (advice.causes or advice.question):
        return brief
    return {
        **brief,
        "expert_diag": {
            "key": problem_key(problem),
            "problem": advice.problem,
            "causes": advice.causes[:MAX_CAUSES],
            "question": advice.question,
            "at": datetime.now(UTC).isoformat(),
        },
    }


def cached(brief: dict[str, Any] | None, noted: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The cached diagnosis when it still describes the main problem, else None (stale)."""
    stored = (brief or {}).get("expert_diag")
    problem = main_problem(noted)
    if (
        isinstance(stored, dict)
        and problem is not None
        and stored.get("key") == problem_key(problem)
    ):
        return stored
    return None


def question_context(brief: dict[str, Any] | None, noted: list[dict[str, Any]]) -> dict[str, Any]:
    """What the brain prompt and the linter get when the expert is on and a main problem is noted:
    the problem, its likely causes and the question that would settle the most uncertain one."""
    problem = main_problem(noted)
    if problem is None:
        return {}
    out: dict[str, Any] = {
        "main_problem": str(problem.get("title") or "")[:120],
        "main_problem_words": " ".join(str(w) for w in problem.get("user_words") or [])[:300],
    }
    if stored := cached(brief, noted):
        out["main_problem_causes"] = [str(c) for c in stored.get("causes") or []][:MAX_CAUSES]
        if stored.get("question"):
            out["suggested_next_question"] = str(stored["question"])
    return out


def given_for(brief: dict[str, Any] | None, problem: dict[str, Any] | None) -> int:
    """Ideas already handed over for this problem (the cap is two per problem)."""
    table = (brief or {}).get("expert_given")
    if not isinstance(table, dict) or problem is None:
        return 0
    return int(table.get(str(problem.get("ref") or problem.get("title") or "")) or 0)


def record_given(
    brief: dict[str, Any], problem: dict[str, Any] | None, count: int
) -> dict[str, Any]:
    if problem is None or count <= 0:
        return brief
    key = str(problem.get("ref") or problem.get("title") or "")
    table = dict(brief.get("expert_given") or {})
    table[key] = int(table.get(key) or 0) + count
    return {**brief, "expert_given": table}
