# ruff: noqa: E501
"""Spec rules wired in brain mode only (lane specrules2). Small, pure helpers; the hot files hold
one-line hooks that call into here.

1. `assumed_industry` (v1.6 G11, TS7, A414, 17.3-N noAssumedIndustry): a reply names no trade
   before the business is confirmed. The detector is `industry_reply_gate`; this is the hook the
   reply guard calls. It is a SOFT check: it only asks for one rewrite (it never blocks a send).
2. `owner_said_links` (PS-7): which pairs of noted problems the OWNER linked in their own words. The
   graph (`problem_graph`) verifies the words (a causal connective in one owner sentence naming
   both problems); a model-written link op can never claim `owner_said` by itself. A guess stays
   `pi_inferred`.
3. `guess_causes` (PS-7 into PS-4): the graph's possible causes for a problem, as `pi_inferred`
   causes labelled as pi's own guess, for the blueprint. Never `owner_said`, never `confirmed`.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from app.modules.pi import industry_reply_gate, problem_graph

_GUESS = {
    "en": "my own guess, to check",
    "roman_ur": "meri apni andaza, check karna hai",
    "ur": "میرا اپنا اندازہ، جانچنا باقی ہے",
    "ar": "تخميني الشخصي، يحتاج إلى تحقق",
    "hi": "मेरा अपना अंदाज़ा, जाँचना बाकी है",
}


def _texts(context: Mapping[str, Any]) -> list[str]:
    """Everything the owner has written so far in this conversation (history, burst, latest)."""
    out = [
        str(h.get("text") or "")
        for h in context.get("history") or []
        if isinstance(h, Mapping) and h.get("role") == "customer"
    ]
    out += [str(t) for t in context.get("burst_texts") or []]
    out.append(str(context.get("latest_customer_message") or ""))
    return [t for t in out if t]


def assumed_industry(reply: str, context: Mapping[str, Any]) -> str | None:
    """The rewrite reason when a reply names a trade the owner never said and the business is not
    confirmed (`industry_unconfirmed` is set where the knowledge is blanked); else None."""
    unconfirmed = context.get("industry_unconfirmed")
    if unconfirmed is None and context.get("pi_mode") == "brain":
        # Industry packs off (or no pack fits): nothing set the flag, but the model can still guess
        # a trade of its own (Chat A, "AC units, spare parts and gas"). Unconfirmed until the
        # brief or the stored profile holds the trade; the owner's own words always clear a noun.
        brief = context.get("brief") or {}
        profile = brief.get("business_profile") or {}
        keys = {str(f.get("key")) for f in profile.get("facts") or [] if isinstance(f, Mapping)}
        unconfirmed = not (brief.get("industry_confirmed") or keys & {"business_type", "industry"})
    if not unconfirmed:
        return None
    found = industry_reply_gate.unconfirmed_industry_noun(
        reply,
        _texts(context),
        trade_confirmed=False,
        language=str(context.get("reply_language") or ""),
    )
    return found.reason if found else None


def owner_said_links(
    problems: Sequence[Mapping[str, Any]], owner_texts: Iterable[str], language: str = "en"
) -> list[tuple[str, str]]:
    """(cause id, effect id) pairs the owner themselves linked: an owner-stated edge of the graph
    that is not a hypothesis. Never raises."""
    texts = [t for t in owner_texts if isinstance(t, str) and t.strip()]
    if len(problems) < 2 or not texts:
        return []
    graph = problem_graph.build_problem_graph(list(problems), texts, None, language)
    pairs: list[tuple[str, str]] = []
    for edge in graph.edges:
        if (
            edge.kind == problem_graph.EdgeKind.OWNER_STATED
            and edge.evidence_status == "owner_said"
            and not edge.hypothesis
            and not edge.hedged
            and edge.from_id != edge.to_id
            and (edge.from_id, edge.to_id) not in pairs
        ):
            pairs.append((edge.from_id, edge.to_id))
    return pairs


def guess_causes(
    problem: Mapping[str, Any], owner_messages: Sequence[str], language: str = "en", limit: int = 2
) -> list[dict[str, Any]]:
    """Possible causes of one problem for the blueprint: `pi_inferred`, no evidence words, the text
    starts with the label that says it is pi's own guess. Empty when the owner already gave a
    cause (theirs wins) or the graph has nothing."""
    if (problem.get("cause_raw") or {}).get("text"):
        return []
    label = _GUESS.get(language, _GUESS["en"])
    hyps = problem_graph.hypotheses_for(
        dict(problem), {"owner_messages": list(owner_messages)}, language
    )
    return [
        {"text": f"{h.text} ({label})", "status": "pi_inferred", "evidence": {}}
        for h in hyps[:limit]
        if h.text
    ]


# --- DQ1 / EO3: "do you know my business?" is answered "not yet", then the link is asked ---------
# Spec v1.6 19.3: the first sentence of the reply answers the direct question. The check runs only
# when pi really knows nothing (no stated facts, no link read); otherwise "yes" may be honest.

_KNOW_ASK = re.compile(
    r"\b(?:do|does) you (?:know|have any idea|understand) (?:anything )?(?:about )?(?:my|our) "
    r"(?:business|work|company|shop)\b"
    r"|\bwhat do you know about (?:my|our) (?:business|work|company|shop)\b"
    r"|\b(?:aap|ap|aapko|ap ko|aap ko|tum) (?:ko )?(?:meri|mere|hamare|hamari|humare) "
    r"(?:business|karobar|kaam|dukaan|company)(?: ke| k)?(?: baare| bare| baray| mutaliq)? "
    r"(?:mein |me |mai )?(?:kuch )?(?:pata|maloom|malum|jaante|janty)\b"
    r"|\b(?:aap|ap|aapko|ap ko|aap ko) (?:ko )?iske? ?(?:baare|bare|baray) (?:mein |me |mai )?kuch "
    r"(?:pata|maloom)\b"
    r"|هل (?:تعرف|تعلم) (?:شيئا |شيئًا )?عن (?:عملي|شركتي|تجارتي|نشاطي|مشروعي)"
    r"|(?:کیا )?(?:آپ|اپ) (?:کو )?(?:میرے|ہمارے) (?:کاروبار|کام|دکان|کمپنی)"
    r"(?: کے بارے میں)? (?:کچھ )?(?:پتا|معلوم|پتہ)"
    r"|क्या (?:आपको|तुम्हें|आप|तुम) (?:को )?(?:मेरे|हमारे) (?:बिज़नेस|बिजनेस|कारोबार|काम|दुकान|कंपनी)"
    r"(?: के बारे में)? (?:कुछ )?(?:पता|मालूम|जानते)",
    re.IGNORECASE,
)
_NOT_YET = re.compile(
    r"\bnot yet\b|\bnot really\b|\bnot much yet\b|\bno,? not yet\b|\bnothing yet\b"
    r"|\babhi (?:nahi|nahin|nhi|tak nahi|tak nahin)\b|\bfilhal nahi\b|\babhi kuch nahi\b"
    r"|ابھی نہیں|ابھی تک نہیں|فی الحال نہیں|ابھی کچھ نہیں"
    r"|ليس بعد|ليس حتى الآن|لا،? ليس بعد|ليس بعد\b|ليس حاليا|لا أعرف بعد"
    r"|अभी नहीं|अभी तक नहीं|फ़िलहाल नहीं|फिलहाल नहीं|अभी कुछ नहीं",
    re.IGNORECASE,
)
_LINK_ASK = re.compile(r"\blink\b|\bwebsite\b|\bpage\b|لنک|ویب|رابط|موقع|صفحة|लिंक|वेबसाइट|पेज", re.I)
_FIRST = re.compile(r"(?<=[.!?؟۔।])\s+")


def _knows_nothing(context: Mapping[str, Any]) -> bool:
    profile = (context.get("brief") or {}).get("business_profile") or {}
    return not profile.get("facts") and not (context.get("shared_links") or [])


def knows_business_ask(text: str) -> bool:
    return bool(_KNOW_ASK.search(" ".join((text or "").split())))


def know_business_problem(reply: str, context: Mapping[str, Any]) -> str | None:
    """DQ1: asked whether pi knows the business, and it knows nothing yet: the first sentence is an
    honest "not yet" and the reply asks for the link. None when it does."""
    if not knows_business_ask(str(context.get("latest_customer_message") or "")):
        return None
    if not _knows_nothing(context):
        return None
    parts = [p for p in _FIRST.split(reply.strip()) if p]
    if parts and _NOT_YET.search(parts[0]) and _LINK_ASK.search(reply):
        return None
    return (
        "they asked whether you know their business and you know nothing about it yet: the FIRST "
        "sentence is an honest 'not yet' (never claim to know it), then ask them to send the link "
        "to their page or website so you can look"
    )


# --- EO2: a correction from the owner is owned in the first clause --------------------------------
_CORRECTION = re.compile(
    r"\bi (?:never|didn'?t|did not|haven'?t|have not) (?:say|said|mention|mentioned|tell|told)\b"
    r"|\bthat'?s not what i (?:said|meant)\b|\bthat is not what i (?:said|meant)\b"
    r"|\byou (?:got|have got|understood) (?:that|it|this) wrong\b|\bthat'?s wrong\b"
    r"|\bmaine (?:aisa |ye |yeh )?(?:kuch )?(?:bhi )?(?:nahi|nahin|nhi) (?:kaha|bola|bataya)\b"
    r"|\bmene (?:aisa |ye |yeh )?(?:kuch )?(?:bhi )?(?:nahi|nahin|nhi) (?:kaha|bola|bataya)\b"
    r"|\b(?:yeh|ye) (?:maine|mene) nahi (?:kaha|bola)\b|\bapne galat (?:samjha|samjhi)\b"
    r"|\baap ne galat (?:samjha|samjhi)\b"
    r"|میں نے (?:ایسا |یہ )?(?:کچھ )?(?:نہیں|نہی) (?:کہا|بتایا)|آپ نے غلط (?:سمجھا|سمجھی)"
    r"|لم أقل (?:ذلك|هذا)|لم أذكر|هذا ليس ما قلته|فهمت(?:ني)? خطأ|فهمتني غلط"
    r"|मैंने (?:ऐसा |यह )?(?:कुछ )?नहीं (?:कहा|बताया)|आपने गलत (?:समझा|समझी)"
    r"|यह मैंने नहीं कहा|मैंने ये नहीं कहा",
    re.IGNORECASE,
)
_OWNS = re.compile(
    r"\bsorry\b|\bapolog|\bmy (?:mistake|bad|error|fault)\b|\byou(?:'re| are) (?:right|correct)\b"
    r"|\bi (?:got|had) (?:that|it|this) wrong\b|\bi misunderstood\b|\bi misheard\b|\bthank(?:s| you) for correcting\b"
    r"|\bmaaf\b|\bmaafi\b|\bmuaaf\b|\bmeri (?:ghalti|galti)\b|\bghalti (?:meri|hui|ho gayi)\b"
    r"|\baap (?:theek|sahi|thik) (?:keh|kah) rahe\b|\bmain ne galat (?:samjha|suna)\b"
    r"|معذرت|معاف|میری غلطی|غلطی میری|آپ (?:ٹھیک|صحیح) (?:کہہ|کہ) رہے|میں نے غلط سمجھا"
    r"|آسف|عذرا|اعتذر|خطأي|غلطتي|معك حق|أنت محق|فهمت خطأ|أخطأت"
    r"|माफ़|माफ|खेद|मेरी गलती|मेरी ग़लती|आप सही|मैंने गलत समझा",
    re.IGNORECASE,
)
_CLAUSE = re.compile(r"[.!?؟۔।,،;:\n]")


def correction_said(text: str) -> bool:
    return bool(_CORRECTION.search(" ".join((text or "").split())))


def correction_not_owned(reply: str, context: Mapping[str, Any]) -> str | None:
    """EO2: the owner corrects pi; the first clause of the reply owns it (sorry, my mistake, you
    are right). None when it does or when the message is no correction."""
    if not correction_said(str(context.get("latest_customer_message") or "")):
        return None
    first = _CLAUSE.split(reply.strip(), maxsplit=1)[0]
    second = reply.strip()[len(first) :][:60]
    if _OWNS.search(first) or (len(first.split()) <= 3 and _OWNS.search(first + second)):
        return None
    return (
        "the owner corrected you: own it in the FIRST clause (for example 'Sorry, my mistake'), "
        "drop the wrong fact, then go on; do not ask a question before owning it"
    )
