# ruff: noqa: E501  (long regexes and fixed lines read better on one line)
"""Free ideas on request, "how exactly?", the Workzap line and the free-rider signal (Addendum 2 to
the pi Brain v3, Parts 1.4 to 1.6 and 1.9), for the live chat.

Pure functions. `solution_context` hands pi the ideas (at most two, none repeated) and this module
decides when the person is asking for them, what the "how exactly?" answer must name, which bridge
opener and build phrase the Workzap line uses, and when the application adds the offer itself. The
offer is never written by the model: it is appended after the reply and moves the chat to S5, so a
later "haan" goes through the explicit-yes gate.
"""

import re
from typing import Any

from app.modules.pi import solutions
from app.modules.pi.problems import what_now

# Asking for a fix, in any of the ways owners put it (Part 1.6). A cost question is not one.
# Always addressed to pi: "fix", "hal", "ideas" or "suggest" alone are part of describing a
# problem ("we fix phones", "koi hal nahi", "no idea why they leave").
SOLUTION_ASK = re.compile(
    r"\b(?:can you (?:tell me|give me|help|fix|make|suggest|do something)|could you (?:help|fix)|"
    r"do you have (?:a |any )?(?:solution|fix|idea)|(?:give|tell) me (?:a |the |some |your )?"
    r"(?:solution|fix|ideas?)|what can you do|what would you build|what should i do|"
    r"solution (?:do|dw|dein|de do|dedo|dena|dijiye|dijie|batao|btao|chahiye)|kya solution (?:hai|he)|"
    r"(?:ye|yeh|yehi|yahi|ise|isay|wo|woh)(?: \w+){0,2} (?:bnwao|banwao|bnao|banao|bana do|bna do|bnwa do|banwa do)|"
    r"(?:ap|aap|tum) (?:ye |yeh |mere liye )?(?:bnwa|banwa|bana|bna)(?:o| do| dein| den)|"
    r"can you (?:build|create) (?:it|this|that)|"
    r"(?:tumhare|aapke|apke) paas (?:koi )?(?:solution|hal)|mujhe (?:koi )?(?:solution|hal) chahiye|"
    r"(?:kuch|kya) kar sakte|kar sakte (?:ho|hain) ya nahi|kya karun|kya karna chahiye|"
    r"(?:koi )?mashwara (?:do|dein|chahiye)|kuch batao"
    r"|hal (?:batao|btao|bataiye|bataen|dein|do|chahiye)|(?:koi )?hal bata\w*)\b"
    # Arabic and Urdu script: "give me a solution", "any solution?", "what is the solution"
    r"|(?:اعطيني|أعطني|عطيني|اعطني|أبغى|ابغى|أريد|اريد|ابي|أبي)\s+(?:لي\s+)?(?:حل|حلا|حلاً|الحل)"
    r"|给我.{0,6}(?:建议|方案|办法|想法|主意)|有(?:什么|哪些)(?:建议|办法|方案|解决)|(?:怎么|如何)(?:解决|处理)|解决(?:办法|方案)"
    r"|(?:وش|ما|ايش|إيش)\s+(?:هو\s+)?الحل|(?:هل )?(?:عندك|عندكم)\s+حل"
    r"|(?:کوئی\s+)?حل\s+(?:بتائیں|بتاو|بتاؤ|دیں|دو|چاہیے|چاہئے)|مجھے\s+(?:کوئی\s+)?حل\s+چاہی",
    re.IGNORECASE,
)
# The same ask in the plain ways owners write it. Each needs the ask itself ("any solution?" at the
# end, "what can we do about it"), so "any idea why they leave" and "we fix phones" stay problems.
SOLUTION_ASK_PLAIN = re.compile(
    r"\bany (?:solutions?|suggestions?|ideas?|advice|fix(?:es)?|way(?: out)?|help)\s*[?.!]*\s*$"
    r"|\bany (?:solutions?|suggestions?|ideas?|advice|fix(?:es)?|way(?: out)?|help) (?:for|to|on) (?:this|it|that)\b"
    r"|\bany (?:solutions?|suggestions?|ideas?)\s*[?]"
    r"|\bwhat (?:can|could|should|do) (?:we|i) do(?: about (?:it|this|that|these))?\b"
    r"|\bhow (?:can|could|should|do|would) (?:we|i) (?:fix|solve|handle|deal with|stop|reduce|prevent|avoid|improve|sort out|manage) (?:it|this|that|these|them)\b"
    r"|\bhow (?:to|do i|do we) (?:fix|solve|handle|stop|sort out) (?:it|this|that)\b"
    r"|\b(?:more|other|another|some|few|different) (?:ideas?|solutions?|suggestions?|options?)\b"
    r"|\b(?:aur|or|ek aur|mazeed|mzeed|aur koi|or koi|koi aur|dusra|dosra|doosra)\s+(?:idea|ideas|solution|hal|mashwara|suggestion)s?\b"
    r"|\b(?:idea|ideas|suggestion|suggestions)\s+(?:dw|dy|do|dein|den|dena|de|dijiye|btao|batao|chahiye|chahye)\b"
    r"|\b(?:can you )?(?:give|provide|share|send|show|tell) (?:me |us )?(?:my |our |the |a |your )?(?:problem |problems )?(?:solutions?|fix|ideas?|suggestions?)\b"
    r"|\b(?:problem|problems|masla|masle|masail) (?:ka |ke |ki )?(?:solution|hal)\b"
    r"|\bhal (?:tw |to |zara |bhi |kya )?(?:batao|btao|bataiye|bataen|hai)\b"
    r"|\b(?:de|dey|dy)\s+(?:sakte|sakty|skte|skty|sakta|sakti)\s*(?:hain|ho|hai|he)?\s*(?:koi\s+)?(?:solution|hal|idea|mashwara)\b"
    r"|\b(?:dein|den|do|dijiye|dijie|dedo|de do)\s+(?:mujhe\s+|mujeh\s+|mujy\s+)?(?:koi\s+)?(?:solution|hal|idea|mashwara)\b"
    r"|\b(?:ke|ky|iske|uske|usky|isky|is ke|us ke)\s+liye\s+(?:koi\s+)?(?:idea|hal|solution|mashwara)\b"
    r"|\bwhat (?:do|would|will) you (?:suggest|recommend|advise)\b"
    r"|\b(?:suggest|recommend) (?:something|anything|a (?:way|fix|solution))\b"
    r"|\b(?:iska|is ka|isay|ise|isko|inka|in ka) (?:hal|solution|ilaj)\b"
    r"|\b(?:theek|thik|sahi|hal) (?:kaise )?(?:karein|karen|kare|karun|karu|hoga)\b"
    r"|\bkya (?:karein|karen|kare|karna hai|karna chahiye)\b"
    # live chats: "Solution dain", "solution?", "Let me know a solution", "mujhe solution den",
    # "koi solution hai iska?", "solution bataye"
    r"|^\W*(?:solutions?|hal|ilaj|ideas?|suggestions?)\W*$"
    # impatience and "what do you do" phrasings from the platform spec's audit chats
    r"|\bkya (?:aap|ap|tum) (?:ye |yeh |ise |isay |isko )?(?:kar|kr) (?:sakte|skte) (?:ho|hain|hn)\b"
    r"|\bseedha (?:batao|bataiye|bata do|btao)\b|\bkahin aur jaun\b|\baap log (?:karte|krte) kya\b"
    r"|\bkya (?:bana|bna) (?:sakte|skte) (?:ho|hain|hn)\b|\bkab se (?:pooch|puch)\w* (?:raha|rha)\b"
    r"|\bsolutions? (?:dain|dayen|den|dijiye|dijie|bataye|bataiye|bata do|batain|batayen)\b"
    r"|\b(?:let me know|tell me|show me|need|want) (?:a |the |some |your )?(?:solutions?|ideas?|suggestions?)\b"
    r"|\bkoi (?:solution|hal|ilaj|tareeqa|tarika|idea|mashwara) (?:hai|he|hoga)\b(?!\s*(?:nahi|nhi))",
    re.IGNORECASE,
)
COST = re.compile(r"\b(?:how much|kitna|kitne|price|pricing|cost|qeemat|kharcha|quote)\b", re.I)
# "how exactly?", "step by step", "which app?" (Part 1.4): the detail is the solution document.
HOWTO = re.compile(
    r"\bhow exactly\b|\bstep[- ]by[- ]step\b"
    r"|\b(?:ye|yeh|ise|isay|iska|ye sab)\b(?: \w+){0,4} kaise\b[^.!]*[?]|\bexactly kaise\b"
    r"|\b(?:kaunsa|kaunsi|konsa|konsi) (?:software|app|tool|system)\b"
    r"|\b(?:which|what) (?:app|software|tool|system)\b"
    r"|كيف\s+بالضبط|كيف\s+بالتحديد|بالتفصيل\s+كيف|أي\s+(?:تطبيق|برنامج)"
    r"|یہ\s+کیسے|اسے\s+کیسے|بالکل\s+کیسے|کون\s*سا\s+(?:سافٹ ?ویئر|ایپ|ٹول)",
    re.IGNORECASE,
)
WHICH_APP = re.compile(
    r"\b(?:kaunsa|kaunsi|konsa|konsi) (?:software|app|tool)\b|\b(?:which|what) (?:app|software|tool)\b",
    re.IGNORECASE,
)
# Someone collecting ideas without meaning to engage (Part 1.5): dashboard only.
FREE_RIDER_WORDS = re.compile(
    r"\b(?:my client|my agency|for a project|for my client|i am a consultant|i'm a consultant)\b",
    re.IGNORECASE,
)
ENOUGH_HOWTO = 3  # "how exactly?" asked this many times
ENOUGH_DECLINES = 2  # or the offer declined this many times

IN_THE_DOCUMENT = re.compile(
    r"\s*\b(?:are|is)(?: (?:set|settled|decided|agreed|fixed|written|worked out|covered))?"
    r" in the solution document\.?\s*$|\s*\bsolution document mein\b.*$",
    re.I,
)


# The word for "solution" / "idea" / "suggestion" in the languages pi has no phrase bank for. A short
# message that holds one is an ask ("tolong kasih solusi", "راه حل بده", "dame una solución"); a long
# one is a story that happens to use the word, and the bare "idea" of Spanish and Italian is left
# out because "no idea why they leave" is a problem in English.
OTHER_LANGUAGE_NOUN = re.compile(
    r"\b(?:solusi|ide|saran|jalan keluar|idée|idee|conseils?|solución|sugerencia|consejo|"
    r"soluzione|soluções?|solução|çözüm|öneri|fikir|lösung|vorschlag|oplossing|решени\w*|совет\w*)\b"
    r"|راه\s*حل|راهکار|راه‌حل|پیشنهاد|समाधान|उपाय|सुझाव|आइडिया|解决|建议|办法|方案|해결|제안|解決|アイデア",
    re.IGNORECASE,
)
OTHER_LANGUAGE_WORDS = 9
# French shares "solution" with English, so only its asking forms count here
FRENCH_ASK = re.compile(
    r"\b(?:donne[zr]?-?moi|avez-vous|auriez-vous|as-tu|propose[zr]?(?:-moi)?)\b[^.?!]{0,25}\bsolution\b",
    re.IGNORECASE,
)


def asks_in_other_language(text: str) -> bool:
    if FRENCH_ASK.search(text):
        return True
    return (
        len(text.split()) <= OTHER_LANGUAGE_WORDS
        and bool(OTHER_LANGUAGE_NOUN.search(text))
        and not re.search(
            r"\b(?:no|sin|ohne|keine?|nessuna?|nenhuma?|tidak ada)\s+\w*$", text, re.I
        )
    )


def asked_for_ideas(said: str) -> bool:
    """They want a fix now: "solution do", "kuch kar sakte ho?", "what can you do?"."""
    text = said or ""
    if COST.search(text) and not (SOLUTION_ASK.search(text) or SOLUTION_ASK_PLAIN.search(text)):
        return False
    return bool(
        SOLUTION_ASK.search(text)
        or SOLUTION_ASK_PLAIN.search(text)
        or what_now(text)
        or asks_in_other_language(text)
    )


def asked_howto(said: str) -> bool:
    return bool(HOWTO.search(said or ""))


def asked_which_app(said: str) -> bool:
    return bool(WHICH_APP.search(said or ""))


def covers(problem: dict[str, Any] | None) -> str:
    """What the solution document settles for this problem, in the entry's own words: the answer to
    "how exactly?" names it (two or three things) instead of giving the steps."""
    stops = " ".join(str((problem or {}).get("free_stops") or "").split())
    return IN_THE_DOCUMENT.sub("", stops).strip(" .")


def bridge(
    brief: dict[str, Any],
    problem: dict[str, Any] | None,
    language: str,
    sector: str | None = None,
) -> dict[str, Any] | None:
    """The Workzap line for one problem (Part 1.9): the build said as what the owner would notice,
    with the next bridge opener not yet used in this chat. Once per problem: a problem that already
    had its line is referred back to in a few words (RBUILD03)."""
    if not problem:
        return None
    keys = (problem.get("workzap_build") or {}).get("keys") or []
    if not keys:
        return None
    said = [str(x) for x in brief.get("builds_said") or []]
    if str(problem.get("id")) in said:
        return {"refer_back": True}
    used = {int(i) for i in brief.get("bridge_used") or []}
    key = "roman_ur" if language == "roman_ur" else "en"
    order = [
        i for i, opener in enumerate(solutions.BRIDGE_OPENERS) if opener[key] and i not in used
    ]
    index = order[0] if order else len(solutions.BRIDGE_OPENERS) - 1  # the one with no opener
    return {
        "says": solutions.build_phrase(keys[0], language, sector),
        "opener": solutions.BRIDGE_OPENERS[index][key],
        "_index": index,
        "_problem": str(problem.get("id")),
    }


def remember_bridge(brief: dict[str, Any], line: dict[str, Any] | None) -> dict[str, Any]:
    """The brief with this Workzap line recorded, so neither it nor its opener comes again."""
    if not line or "_problem" not in line:
        return brief
    return {
        **brief,
        "builds_said": [*list(brief.get("builds_said") or []), line["_problem"]][-40:],
        "bridge_used": [*list(brief.get("bridge_used") or []), line["_index"]][-12:],
    }


def public(line: dict[str, Any] | None) -> dict[str, Any] | None:
    """The line without its bookkeeping keys, for the prompt."""
    return {k: v for k, v in line.items() if not k.startswith("_")} if line else None


def free_rider(brief: dict[str, Any], said: str) -> bool:
    """signal.possible_free_rider: logged for the dashboard only, pi's tone never changes."""
    return (
        int(brief.get("howto_asked") or 0) >= ENOUGH_HOWTO
        or int(brief.get("declines") or 0) >= ENOUGH_DECLINES
        or bool(FREE_RIDER_WORDS.search(said or ""))
    )


OFFER_AFTER = {
    "en": "Shall I get a solution document and a quote made for you? You can say no.",
    "roman_ur": "Kya main aap ke liye solution document aur quote banwa doon? Mana bhi kar sakte hain.",
    "ar": "هل أجهّز لك وثيقة حل وعرض سعر؟ يمكنك أن تقول لا.",
}
OFFERABLE = ("S1_LISTENING", "S2_CLARIFYING", "S3_NOTED", "S4_SORTED_SUMMARY")
# Where a request for a fix or for the detail may be answered: while listening, and at the offer
# (never in the payment, document or delivery states).
ASKABLE = (*OFFERABLE, "S5_READINESS", "S5b_DECLINED")


def offer_line(language: str | None) -> str:
    return OFFER_AFTER.get(language or "en", OFFER_AFTER["en"])


OFFERS_DOCUMENT = re.compile(
    r"(?:solution document|document (?:and|aur|&) (?:a |an )?quote|quote (?:and|aur) (?:a )?document)"
    r"[^.?!\n]{0,80}[?؟]\s*$",
    re.IGNORECASE,
)


def already_offers(reply: str) -> bool:
    """The reply already ends by asking whether to prepare the solution document and quote (a
    model sometimes writes the offer itself): the application must not add its own on top."""
    return bool(OFFERS_DOCUMENT.search((reply or "").rstrip()))
