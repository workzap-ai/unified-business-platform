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
    # heavy short Roman Urdu spellings from a live chat: "solution ap dw", "solution dy",
    # "ap kya kr skty hain", "kya kar skty hain wo btyn", "hal btyn"
    r"|\b(?:solution|sol|hal|idea|ideas|mashwara|suggestion)s?\s+(?:(?:ap|aap|app)\s+)?"
    r"(?:dw|dy|dyn|de|do|dein|den|dain|dijiye|dedo|dena|btyn|batayen|batain|bataen|bataiye|btao|batao)\b"
    r"|\b(?:ap|aap|app)\s+(?:solution|hal|idea|mashwara)\s+(?:dw|dy|dyn|de|do|dein|den|dain)\b"
    r"|\b(?:ap|aap|app|tum)?\s*kya\s+(?:kar|kr)\s+(?:sakte|skte|skty|sakty|sakta|skta)\b"
    r"|\bkuch\s+(?:kar|kr)\s+(?:sakte|skte|skty|sakty)\b"
    # "koi idea?" / "koi hal?" and the same asks in the other languages pi serves
    r"|\bkoi (?:idea|hal|solution|mashwara|tareeqa)\s*[?؟]"
    r"|\b(?:tienes|tiene|hay) (?:alguna|una) idea\b|\bfikr\w* var m[ıi]\b|\bbir (?:öneri|fikir)\b"
    r"|\bcomment (?:commencer|d[ée]marrer|d[ée]buter)\b|\bpar o[uù] commencer\b"
    r"|\b(?:c[óo]mo|por d[óo]nde) (?:empezar|comenzar|iniciar)\b"
    r"|\b(?:bagaimana|gimana) (?:cara )?(?:memulai|mulai)\b|\bcara (?:memulai|mulai)\b"
    r"|\bnas[ıi]l (?:ba[şs]lar[ıi]m|ba[şs]layabilirim|ba[şs]lamal[ıi]y[ıi]m|ba[şs]lan[ıi]r)\b"
    r"|\bwie (?:fange|beginne|starte) ich\b"
    r"|怎么开始|如何开始|怎样开始|从哪里开始|كيف (?:أبدأ|ابدأ|نبدأ)|من أين أبدأ"
    r"|कैसे (?:शुरू|शुरुआत)|कहाँ से शुरू|چطور شروع|چگونه شروع|از کجا شروع|کیسے شروع|کہاں سے شروع"
    # "how do I begin" (a would-be founder, a live replay): English and Roman Urdu
    r"|\bhow (?:to|do i|can i|should i) (?:start|begin|get started|take (?:the )?first step)\b"
    r"|\bwhere (?:do i|to|should i) (?:start|begin)\b|\bwhat (?:should i|do i) do first\b"
    r"|\bhow to do\s*[?.!]*\s*$"
    r"|\b(?:what(?:'s| is)|which|tell me) (?:the )?first step\b"
    r"|\bkaise (?:shuru|start|shuruaat) (?:karun|karoon|karon|kare|karein|krun|karna|karen)\b"
    r"|\bkahan se (?:shuru|start)\b|\bshuru kaise\b|\bpehla (?:qadam|step|kaam)\b"
    r"|\b(?:pehle|pehla) (?:kya|kia) (?:karun|karoon|krun|kare|karna)\b"
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


# What a model said about a message the phrase banks do not know (ask_classifier). Kept for that exact
# text only, bounded, and only ever consulted when the phrase banks say "not an ask".
_LEARNED_ASKS: dict[str, bool] = {}
LEARNED_LIMIT = 500


def remember_ask(said: str, value: bool) -> None:
    if len(_LEARNED_ASKS) >= LEARNED_LIMIT:
        _LEARNED_ASKS.pop(next(iter(_LEARNED_ASKS)))
    _LEARNED_ASKS[said or ""] = value


def known_ask(said: str) -> bool | None:
    return _LEARNED_ASKS.get(said or "")


_SOLUTION_TYPOS = ("solution", "solutions", "solushan", "solusion")
_GIVE_TYPOS = {"dw": "do", "dyn": "dein", "dain": "dein", "dijye": "dijiye", "dejiye": "dijiye"}


def fix_typos(text: str) -> str:
    """Quick typing of the ask ("soluton dw", "solutin do") read as what was meant. Only the word
    "solution" and the few ways of saying "give" that people shorten; every other word is kept."""
    import difflib

    if not text or len(text) > 120:
        return text
    words = text.split()
    fixed: list[str] = []
    for word in words:
        bare = re.sub(r"[^\w]", "", word).lower()
        if 6 <= len(bare) <= 10 and difflib.get_close_matches(bare, _SOLUTION_TYPOS, 1, 0.82):
            fixed.append("solution")
        elif bare in _GIVE_TYPOS and any(
            w in _SOLUTION_TYPOS or w.startswith("solu") for w in (x.lower() for x in words)
        ):
            fixed.append(_GIVE_TYPOS[bare])
        else:
            fixed.append(word)
    return " ".join(fixed)


def asked_for_ideas(said: str) -> bool:
    """They want a fix now: "solution do", "kuch kar sakte ho?", "what can you do?"."""
    fixed = fix_typos(said or "")
    # as typed first (other languages' own words), then with the typing slips read as meant
    return _asked_for_ideas(said or "") or (fixed != (said or "") and _asked_for_ideas(fixed))


# "Do something", the most common way an owner asks for a fix in Roman Urdu: "kuch karo", "kuch kro",
# "kuch to kijiye", "kuch kar do". A refusal ("kuch nahi karna") is not an ask.
DO_SOMETHING = re.compile(
    r"\bkuch (?:to |bhi )?(?:kar|kr|karo|kro|karen|kren|kare|kre|kijiye|kijye|kijiyega|kardo|krdo)\b",
    re.IGNORECASE,
)
REFUSAL_NEAR = re.compile(r"\b(?:nahi|nhi|mat|na)\b", re.IGNORECASE)


def _asked_for_ideas(text: str) -> bool:
    if DO_SOMETHING.search(text) and not REFUSAL_NEAR.search(text):
        return True
    if COST.search(text) and not (SOLUTION_ASK.search(text) or SOLUTION_ASK_PLAIN.search(text)):
        return False
    return bool(
        SOLUTION_ASK.search(text)
        or SOLUTION_ASK_PLAIN.search(text)
        or what_now(text)
        or asks_in_other_language(text)
        or CHURN.search(text)
        or _LEARNED_ASKS.get(text) is True
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
    preferred = str(brief.get("bridge_preferred") or "")  # the learned choice (A2-FIX-5)
    if preferred:
        match = next((i for i in order if solutions.BRIDGE_OPENERS[i][key] == preferred), None)
        index = index if match is None else match
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
    "en": "Shall I get one solution document and a quote made for all of these together? You can say no.",
    "roman_ur": "Kya main in sab ke liye ek solution document aur quote banwa doon? Mana bhi kar sakte hain.",
    "ar": "هل أجهّز لكل هذه المشكلات وثيقة حل واحدة وعرض سعر؟ يمكنك أن تقول لا.",
}
OFFERABLE = ("S1_LISTENING", "S2_CLARIFYING", "S3_NOTED", "S4_SORTED_SUMMARY")
# Where a request for a fix or for the detail may be answered: while listening, and at the offer
# (never in the payment, document or delivery states).
ASKABLE = (*OFFERABLE, "S5_READINESS", "S5b_DECLINED")


def rejects_ideas(text: str | None) -> bool:
    """The person says the ideas were wrong or not what they asked ("solution glt hai again den",
    "ye nahi", "not what I asked"): a request for different ideas, never silence."""
    from app.modules.pi import solution_score

    reaction = solution_score.classify(text or "")
    return bool(reaction and reaction.signal in ("idea_generic", "idea_no_help"))


def offer_line(language: str | None, context: dict[str, Any] | None = None) -> str:
    """The offer, in the person's language: one of the eight priority languages by the script and
    words of their message, else the chat's language."""
    from app.modules.pi import fixed_lines

    base = OFFER_AFTER.get(language or "en", OFFER_AFTER["en"])
    if context is None:
        return base
    return fixed_lines.line("offer", fixed_lines.code(context), base)


OFFERS_DOCUMENT = re.compile(
    r"(?:solution document|document (?:and|aur|&) (?:a |an )?quote|quote (?:and|aur) (?:a )?document)"
    r"[^.?!\n]{0,80}[?؟]\s*$",
    re.IGNORECASE,
)


def already_offers(reply: str) -> bool:
    """The reply already ends by asking whether to prepare the solution document and quote (a
    model sometimes writes the offer itself): the application must not add its own on top."""
    return bool(OFFERS_DOCUMENT.search((reply or "").rstrip()))


# An owner losing patience ("kab se pooch raha hoon", "jaldi", "time nahi hai", "already asked"):
# the reply starts with a short apology and gives the ideas, with no question before them
# (platform spec Book 4, G27).
IMPATIENT = re.compile(
    r"\bk[au]b s(?:e|ay) (?:pooch|puch)\w*\b|\bpooch\w* (?:raha|rha|rahi) (?:hoon|hun|hu|hoan)\b|\bjaldi\b"
    r"|\btime nahi (?:hai|he)\b|\bsawal hi\b|\bkitne sawal\b|\bitne sawal\b|\bbar bar\b"
    r"|\b(?:i have|i've|already) (?:been )?ask(?:ed|ing)\b|\bhow many times\b|\bfor the (?:third|fourth|fifth) time\b"
    r"|\bstop asking\b|\bjust (?:tell|give) me\b|\bseedha batao\b|\bcome on\b",
    re.IGNORECASE,
)


def impatient(said: str) -> bool:
    return bool(IMPATIENT.search(said or ""))


# An owner about to leave ("rehne do, koi aur dekh leta hoon", "I'll look elsewhere"): pi reassures
# in one line and gives the ideas in the same message (platform spec Book 2, G18). The same cue is
# what the dashboard's churn alert reads.
CHURN = re.compile(
    r"\brehne do\b[^.?!]{0,20}\bkoi aur\b|\bkoi aur dekh\w*\b|\bkahin aur (?:jaun|jaaun|chala)\w*\b"
    r"|\b(?:i(?:'ll| will)|let me) (?:look|check|try) (?:elsewhere|somewhere else|another)\b",
    re.IGNORECASE,
)


def churn_risk(said: str) -> bool:
    return bool(CHURN.search(said or ""))
