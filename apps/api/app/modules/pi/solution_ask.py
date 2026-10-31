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

from app.modules.pi import owner_asks, solutions
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


# A sentence that only DESCRIBES their business or their customers, with a word that also appears in
# real asks ("we provide solutions", "clients need solutions", "kuch bhi kar lete hain", "marizon ko
# ilaj chahiye", "other options nearby"). Never an ask for ideas.
NOT_AN_ASK = re.compile(
    r"\b(?:we|our|they|their|my (?:clients?|customers?)|customers?|clients?|patients?|students?)\b"
    r"[^.?!\n]{0,30}\b(?:provide|offer|sell|give|need|want|needs|wants|have|use)\b"
    r"[^.?!\n]{0,25}\b(?:solutions?|ideas?|options?|suggestions?)\b"
    r"|\b(?:other|different|some|few)\s+(?:options?|solutions?)\s+(?:nearby|around|available|in the market)\b"
    r"|\bkuch (?:bhi )?kar (?:lete|leta|leti|lena|ke|kar)\b"
    r"|\b(?:marizon|mareezon|patients?|logon|logo)\s+ko\b[^.?!\n]{0,20}\b(?:ilaj|hal|solution)\b"
    r"|\bke liye\s+(?:ek\s+)?solution\s+(?:use|istemal|lagaya|lagate|karte)\b"
    r"|\bhow to (?:start|begin|use)\b[^.?!\n]{0,20}\b(?:don'?t know|do not know|nahi pata)\b"
    r"|\b(?:don'?t|do not)\s+know\s+how\s+to\s+(?:start|begin|use)\b",
    re.IGNORECASE,
)
# Chinese, Japanese and Korean have no spaces: a long message is a story, not an ask.
_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")


def asked_for_ideas(said: str) -> bool:
    """They want a fix now: "solution do", "kuch kar sakte ho?", "what can you do?"."""
    if NOT_AN_ASK.search(said or ""):
        return False
    if len(_CJK.findall(said or "")) > 24:
        return False
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

# More very common ways to say "what should I do / give me a way / how do I fix this" in Roman Urdu,
# Hindi, Urdu script and Arabic (spelling variants included). STRONG ones are an ask wherever they
# stand; WEAK ones ("koi hal", "kuch batao") also open ordinary sentences ("koi hal nahi mila",
# "unko kuch batao to...") so they count only in a short message. A refusal or "I do not know"
# anywhere in the message ("koi hal nahi", "pata nahi") is never an ask.
EXTRA_REFUSAL = re.compile(
    r"\b(?:nahi|nahin|nhi|nai|mat|pata|maloom|malum|nothing|no|not|dont|don't)\b"
    r"|(?<!\w)(?:نہیں|نہی|مت|معلوم|پتا|پتہ|नहीं|नही|मत|पता|لا|ليس|مش|مو)(?!\w)|ما\s+في",
    re.IGNORECASE,
)
EXTRA_STRONG = re.compile(
    r"\b(?:ab |phir |to |tou |toh )?(?:main |mein |mai |hum |ham |mujhe |mujhy |mjhe )?"
    r"(?:kya|kia|kiya|ky) (?:karun|karoon|karon|krun|krn|karen|karein|kren|krna|karna|karna chahiye|krna chahiye)\b"
    r"|\bkya (?:kiya|kia|kia) (?:jaye|jae|jai|jaaye|jaiye|jayega|jaega)\b"
    r"|\bkaise (?:theek|thik|thek|sahi|durust|solve|fix|hal) (?:ho|hoga|hogi|hogaa|karen|karein|karun|kar sakte)\b"
    r"|\b(?:is|iss|isay|ise|isko)(?: \w+){0,3} kaise (?:nipt|nibt|nibat|nipat)\w*"
    r"|\bhal (?:nikal|nikaal)\w*"
    r"|\b(?:koi )?(?:rasta|raasta|raah|tareeqa|tariqa|tarika|tareeqe|ilaj) (?:batao|btao|bataiye|bataen|batayen|dikhao|dikhaiye|do|dein|chahiye)\b"
    r"|क्या (?:करूं|करूँ|करें|करना चाहिए|किया जाए|किया जाये|करना होगा)"
    r"|(?:मुझे|अब) क्या करना"
    r"|कैसे (?:ठीक|हल|सुलझ)|कोई (?:हल|उपाय|तरीका|समाधान|रास्ता)\s+(?:बताओ|बताइए|बताएं|दो|दीजिए|चाहिए)"
    r"|कुछ (?:करो|कीजिए|कीजिये|कर दो)"
    r"|کیا\s+(?:کروں|کریں|کر\s+سکتے\s+ہیں|کرنا\s+چاہیے|کرنا\s+چاہئے|کرنا\s+ہوگا|کیا\s+جائے)"
    r"|کیسے\s+(?:ٹھیک|حل|درست)|کچھ\s+(?:کریں|کرو|کیجیے|کیجئے)"
    r"|(?:کوئی\s+)?(?:طریقہ|راستہ|علاج|ترکیب)\s+(?:بتائیں|بتاؤ|بتاو|بتائیے|دیں|دو|چاہیے|چاہئے)"
    r"|ماذا\s+(?:أفعل|افعل|أعمل|اعمل|نفعل|نعمل|يجب\s+أن\s+أفعل|(?:نستطيع|يمكننا|يمكن)\s+أن\s+(?:نفعل|نعمل))|ما\s+العمل\b|كيف\s+(?:أحل|احل|أصلح|اصلح|أعالج|اعالج|أتصرف|اتصرف|أتعامل|اتعامل)"
    r"|(?:شو|وش|ايش|إيش|شنو|شلون)\s+(?:أسوي|اسوي|أعمل|اعمل|أسوّي)"
    r"|(?:أحتاج|احتاج|محتاج)\s+(?:إلى\s+)?(?:حل|نصيحة|اقتراح)|(?:أعطني|اعطني|عطني)\s+(?:نصيحة|اقتراح|اقتراحا)",
    re.IGNORECASE,
)
EXTRA_WEAK = re.compile(
    r"\bkoi (?:hal|haal|tareeqa|tariqa|tarika|tareeqe|rasta|raasta|raah|ilaj|solution|upaay|upay)\b"
    r"|\bkuch (?:to |tou |toh )?(?:bata|btao|batao|bataiye|bataen|batain|batayen|batana|bataye|bataein|btaye|btayen)"
    r"(?:\s+(?:na|please|plz|yar|yaar|ji|ap|aap|zara|do|dein))*\s*[?.!]*$"
    r"|कोई (?:हल|उपाय|तरीका|समाधान|रास्ता)|कुछ (?:बताओ|बताइए|बताएं)"
    r"|کوئی\s+(?:حل|طریقہ|راستہ|علاج)|کچھ\s+(?:بتائیں|بتاؤ|بتاو|بتائیے)"
    r"|(?:أي|اي)\s+حل|هل\s+من\s+حل|ما\s+الحل|(?:نصيحة|اقتراح)\s*[؟?]",
    re.IGNORECASE,
)
EXTRA_WEAK_WORDS = 6  # a longer message is a story that happens to hold the phrase


def asked_in_other_ways(text: str) -> bool:
    """The extra common asks above ("ab kya karun", "koi hal", "kya kiya jaye", "ماذا أفعل")."""
    said = " ".join((text or "").split())
    if not said:
        return False
    # a refusal counts in the sentence that holds it: "sorry, not 20, it was 200. What do we do
    # now?" corrects a figure and then asks (the correction's "not" is not a refusal to be helped)
    for part in re.split(r"(?<=[.!?؟۔])\s+", said):
        if EXTRA_STRONG.search(part) and not EXTRA_REFUSAL.search(part):
            return True
    if EXTRA_REFUSAL.search(said):
        return False
    return len(said.split()) <= EXTRA_WEAK_WORDS and bool(EXTRA_WEAK.search(said))


# An owner who is lost asks for help without the word "solution" (live chat, 2026-10-27: a distributor
# with crores of stock and no visibility said "in sab ko control kaise karun", "aisa system kaise
# banega" and "aap mujhe samjhayen ke kya system banana chahiye" and got five more questions). These
# are a request to be helped. "Samajh nahi aa raha" counts only with "kaise" (how): without it the
# owner is puzzled about a cause ("samajh nahi aa raha ye kyun ho raha hai"), which is not an ask.
IMPLICIT_HELP = re.compile(
    r"\b(?:control|handle|manage|sambhal\w*|sanbhal\w*|theek|thik|solve|fix|monitor)(?: \w+){0,2}"
    r" (?:kaise|kese|kesay|kaisay) (?:karun|karoon|karon|krun|karen|karein|kren|kar sakta|kar sakte)\b"
    r"|\b(?:kaise|kese|kesay|kaisay) (?:control|handle|manage|monitor|sambhal\w*|sanbhal\w*)"
    r"(?: \w+){0,2} (?:karun|karoon|karon|krun|karen|karein|kren)\b"
    r"|\bsystem (?:kaise|kese|kesay|kaisay) (?:banega|banay ga|bnega|bane ga|banayen|bnayen|banaen|banta|ban sakta)\b"
    r"|\bkya (?:system|software|app|tareeqa|tariqa|hal)(?: \w+){0,2} (?:banana|bnana|banani|bnani|banayen|bnayen|lagana|lagani|chahiye|chahie)\b"
    r"|\b(?:aap |ap |app )?(?:mujhe|mujhy|mjhe|hamein|humein)(?: \w+){0,2} (?:samjhayen|samjhaiye|samjhaen|samjhaye|samjha dein|samjha do|samjhao|samjhaiye ga)\b"
    r"|\bsamajh nahi (?:aa|a) raha (?:ke |ki |hai ke )?(?:\w+ ){0,10}(?:kaise|kese|kesay|kaisay)\b"
    r"|\b(?:mujhe|mjhe) (?:kuch )?(?:madad|help|rehnumai|rahnumai|mashwara) (?:chahiye|chahie|do|dein|karen)\b"
    r"|\bhow (?:do|can|should) i (?:control|handle|manage|fix|solve|track|monitor)\b"
    r"|\bwhat (?:system|tool|setup) (?:should|do) (?:i|we) (?:build|need|use|set up)\b"
    r"|\bi (?:don't|dont|do not) know how to (?:control|handle|manage|fix|solve|track)\b"
    r"|मुझे समझ नहीं आ रहा[^.?!\n]{0,60}कैसे|कैसे (?:कंट्रोल|संभाल|ठीक) करूं|कौन सा सिस्टम"
    r"|سمجھ نہیں آ رہا[^.?!\n]{0,60}کیسے|کیسے (?:کنٹرول|سنبھال|ٹھیک) کروں|کون سا سسٹم",
    re.IGNORECASE,
)


def _asked_for_ideas(text: str) -> bool:
    if IMPLICIT_HELP.search(text) and not NOT_AN_ASK.search(text):
        return True
    if DO_SOMETHING.search(text) and not REFUSAL_NEAR.search(text):
        return True
    if asked_in_other_ways(text):
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
    # "pehle kaunsa system banana tha?" asks about the past (what was decided), not how to build
    return bool(HOWTO.search(said or "")) and not owner_asks.asks_for_recall(said)


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
    "en": "Shall I get one solution document and a quote made for all of these together?",
    "roman_ur": "Kya main in sab ke liye ek solution document aur quote banwa doon?",
    "ar": "هل أجهّز لكل هذه المشكلات وثيقة حل واحدة وعرض سعر؟",
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


# The Solution Box offer (platform spec Book 5, 5.4 wording), used only when `brain.box_offer` is
# on; the older document-and-quote line above stays for every other workspace. The spec words the
# soft decline before the question in its first example; the question is kept as the last sentence
# (one question per message, CLAUDE.md), so the order of the sentences is the only change. {n} is
# the number of problems. "A" needs three or more, "B" three or more and a reviewed map.
BOX_OFFERS: dict[str, dict[str, str]] = {
    "en": {
        "A": "So far you've told me about {n} problems, and they've become one picture. It's fine if you don't want this yet, and new problems can keep joining the same box. Shall I write all of them into one Solution Box, in your order, and have Workzap prepare a quote?",
        "B": "The map looks quite complete now. Shall I start writing it up, or is there anything else to look at alongside it?",
        "C": "It's fine if you don't want this yet, and new problems can keep joining the same box. Shall I write all of this into one Solution Box and have Workzap prepare a quote?",
    },
    "roman_ur": {
        "A": "Ab tak aap ne {n} masle bataye, aur wo ek hi tasveer ban gaye hain. Abhi nahi chahiye to bhi theek hai, aur naye masle isi box mein judte jayenge. In sab ko ek Solution Box mein, aap ki tarteeb se, likh dein, aur Workzap ki taraf se ek quote ban jaye?",
        "B": "Naqsha ab kaafi mukammal lagta hai. Likhna shuru karein, ya koi aur baat saath dekhni hai?",
        "C": "Abhi nahi chahiye to bhi theek hai, aur naye masle isi box mein judte jayenge. In sab ko ek Solution Box mein likh dein, aur Workzap ki taraf se ek quote ban jaye?",
    },
    # Other languages carry the neutral form only, written for review by a native speaker (spec
    # decision 10).
    "ur": {
        "C": "اگر ابھی نہیں چاہیے تو بھی ٹھیک ہے، اور نئے مسائل اسی باکس میں جڑتے رہیں گے۔ کیا ان سب کو ایک Solution Box میں لکھ دیں، اور Workzap کی طرف سے ایک کوٹیشن بن جائے؟",
    },
    "ar": {
        "C": "لا بأس إن لم تريد ذلك الآن، ويمكن للمشكلات الجديدة أن تنضم إلى الصندوق نفسه. هل أكتب كل هذا في Solution Box واحد وتجهّز Workzap عرض سعر؟",
    },
    "fr": {
        "C": "Pas de souci si vous n'en voulez pas encore, et les nouveaux problèmes pourront rejoindre la même boîte. Souhaitez-vous que j'écrive tout cela dans une seule Solution Box et que Workzap prépare un devis ?",
    },
    "fa": {
        "C": "اگر هنوز نمی‌خواهید مشکلی نیست، و مشکل‌های تازه می‌توانند به همین جعبه اضافه شوند. آیا همه این‌ها را در یک Solution Box بنویسم و Workzap یک پیش‌فاکتور آماده کند؟",
    },
    "es": {
        "C": "No pasa nada si todavía no lo quiere, y los problemas nuevos podrán seguir sumándose a la misma caja. ¿Quiere que escriba todo esto en una sola Solution Box y que Workzap prepare un presupuesto?",
    },
}
BOX_V2_OFFERS = {
    "en": "{naya}. Shall I add these to a Box v2 and ask Workzap to update the quote?",
    "roman_ur": "{naya}. Kya in ko Box v2 mein jod dein, aur Workzap se quote update karwa dein?",
}


def box_offer_line(context: dict[str, Any]) -> str:
    """The Solution Box offer for this chat: the "A" or "B" wording when the map is rich enough to
    say so (the choice alternates by message so one owner never sees a pattern), else the neutral
    one. After a box was sent and a problem came in, the Box v2 offer with the "Naya:" list."""
    from zlib import crc32

    from app.modules.pi import box_doc, fixed_lines

    code = fixed_lines.code(context)
    key = "roman_ur" if code == "roman_ur" else "en"
    brief = context.get("brief") or {}
    if brief.get("box_naya"):
        naya = box_doc.naya_line([str(t) for t in brief["box_naya"]], key)
        if naya:
            return BOX_V2_OFFERS[key].format(naya=naya)
    count = len(context.get("noted_problems") or [])
    table = BOX_OFFERS.get(code) or BOX_OFFERS[key]
    kinds = [k for k in ("A", "B") if k in table and count >= 3]
    if "B" in kinds and not brief.get("map_reviewed"):
        kinds.remove("B")
    if kinds:
        pick = kinds[crc32(str(context.get("latest_message_id") or "").encode()) % len(kinds)]
    else:
        pick = "C"
    return table[pick].format(n=count)


def offer_line(language: str | None, context: dict[str, Any] | None = None) -> str:
    """The offer, in the person's language: one of the eight priority languages by the script and
    words of their message, else the chat's language. With the Solution Box on (`box_offer`) it is
    the Solution Box wording of the spec."""
    from app.modules.pi import fixed_lines

    base = OFFER_AFTER.get(language or "en", OFFER_AFTER["en"])
    if context is None:
        return base
    if context.get("box_offer"):
        return box_offer_line(context)
    return fixed_lines.line("offer", fixed_lines.code(context), base)


OFFERS_DOCUMENT = re.compile(
    r"(?:solution document|document (?:and|aur|&) (?:a |an )?quote|quote (?:and|aur) (?:a )?document)"
    r"[^.?!\n]{0,80}[?؟]\s*$"
    r"|solution box[^.?!\n]{0,140}[?؟]\s*$",
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
