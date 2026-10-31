# ruff: noqa: E501  (one language per line reads better than wrapped patterns)
"""Reply-linter checks for spec rules that were enforced only in the prompt, or only narrowly.

Pure functions, no model call, no I/O. `check(reply, context)` returns `(rule, message, hard)` tuples
and `constitution.lint` turns each into a `Violation`, so the usual retry (regenerate with the
reason) and repair (safe fallback after a second failure) apply, behind the same brain-mode or
constitution flag as every other linter rule.

Rules (spec v1.6 wins): R-PRIV-08 no pressure for detail they hesitate to give, R-VOICE-11 their
names for things, R-ASK-03 never ask what they already said, R-ASK-04 closed or choice questions
for brief writers, R-ASK-05 a skipped question is not re-asked, R-MEM-02 facts already known,
R-CANT-01/02 a limit is said first and followed by what happens next, X5 business distress is
acknowledged and is not an emergency, R-PROM-02 pi never decides for the person, R-PROM-03 no
forecasts, R-SOL-09 no regulated advice, R-ANS-02 yes/no answered with a yes or a no, R-ECHO-01 one
noted line per problem, R-ECHO-02 bulleted restatements only in the summary.

False positives are worse than misses here: every pattern needs two independent signals (a
hesitation AND a push; a label AND a number the person never used) or a narrow phrase."""

import re
import unicodedata
from typing import Any

from app.modules.pi import constitution_langs as langs
from app.modules.pi import flow

Finding = tuple[str, str, bool]

QUESTION_MARKS = ("?", "؟")
SENTENCE = re.compile(r"(?<=[.!?؟۔।])\s+|\n+")
WORDS = re.compile(r"[^\s.,;:!?؟۔।¿¡()\"«»…\-–—،/]+")
BULLETS = ("•", "- ", "* ")


def _n(text: Any) -> str:
    return unicodedata.normalize("NFC", str(text or "")).replace("’", "'")


def _rx(pattern: str, flags: int = re.IGNORECASE) -> re.Pattern[str]:
    return re.compile(unicodedata.normalize("NFC", pattern), flags)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE.split(text) if s.strip()]


def _tokens(text: str) -> list[str]:
    return [w.lower() for w in WORDS.findall(_n(text))]


def _is_question(sentence: str) -> bool:
    return sentence.rstrip().endswith(QUESTION_MARKS)


def _history(context: dict[str, Any]) -> list[dict[str, Any]]:
    history = context.get("history")
    return [h for h in history if isinstance(h, dict)] if isinstance(history, list) else []


def _customer_texts(context: dict[str, Any]) -> list[str]:
    return [_n(h.get("text")) for h in _history(context) if h.get("role") == "customer"]


def _pi_texts(context: dict[str, Any]) -> list[str]:
    return [_n(h.get("text")) for h in _history(context) if h.get("role") == "ai"]


def _latest(context: dict[str, Any]) -> str:
    return _n(context.get("latest_customer_message")).strip()


def _heard(context: dict[str, Any]) -> str:
    return " ".join([*_customer_texts(context), _latest(context)]).lower()


def _state(context: dict[str, Any]) -> Any:
    flow_state = context.get("flow")
    return flow.parse(flow_state.get("state")) if isinstance(flow_state, dict) else None


# --- content stems, shared by the re-ask and echo checks ---------------------------------------
STOP = frozenset(
    (
        "the and for you your how what which any are was were does did can could would will with that this "
        "have has not but our its they them there then than from into about when where who why also just "
        "more some aur ya hai hain kya ka ke ki ko se mein par aap ap hum ham ho hota hoti hote hoga "
        "کی کا کے کو سے میں پر ہیں ہے ہو آپ یہ وہ اور یا کیا ہوتے ہوتا ہوتی "
        "في من على إلى عن هل ما هو هي أن و أو "
        "की का के को से में पर हैं है हो आप यह वह और या क्या होते होता होती"
    ).split()
)


def _latin(token: str) -> bool:
    return token[:1] < "ɐ"


def _stem(token: str) -> str:
    if _latin(token) and len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def _stems(text: str) -> set[str]:
    out = set()
    for tok in _tokens(text):
        if tok in STOP or tok.isdigit():
            continue
        if len(tok) >= (3 if _latin(tok) else 2):
            out.add(_stem(tok))
    return out


def _same(a: str, b: str) -> bool:
    a, b = _stem(a), _stem(b)
    if a == b:
        return True
    if _latin(a) and _latin(b):
        return min(len(a), len(b)) >= 5 and a[:5] == b[:5]
    return min(len(a), len(b)) >= 4 and a[:3] == b[:3]


def _overlap(a: set[str], b: set[str]) -> float:
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def _last_question(text: str) -> str:
    return next((s for s in reversed(_sentences(text)) if _is_question(s)), "")


# --- R-PRIV-08: never pressure for detail they hesitate to give --------------------------------
HESITATES = _rx(
    r"\brather\s+not\b|\bprefer\s+not\b|\bdon'?t\s+want\s+to\s+(?:say|share|tell|give|discuss|talk)\b"
    r"|\bnot\s+comfortable\b|\bit'?s\s+private\b|\bprivate\b|\bpersonal\b|\bcan'?t\s+share\b|\bwon'?t\s+say\b"
    r"|\bno\s+comment\b|\bnot\s+telling\b"
    r"|\bbatana\s+nahi\b|\bnahi\s+batana\b|\bnahi\s+bata(?:unga|ungi|yenge)\b|\bprivate\s+hai\b|\bzaati\b|\bnahi\s+dena\b|\bshare\s+nahi\b"
    r"|نہیں\s+بتانا|بتانا\s+نہیں|نہیں\s+بتاؤں|پرائیویٹ|ذاتی|شیئر\s+نہیں"
    r"|لا\s+أريد\s+(?:أن\s+)?(?:أقول|أذكر|أشارك|أخبر)|لا\s+أرغب|أفضل\s+ألا|(?<!\S)خاص(?!\S)"
    r"|नहीं\s+बताना|बताना\s+नहीं|निजी|प्राइवेट|शेयर\s+नहीं"
)
PRESSURES = _rx(
    r"\byou\s+(?:must|have\s+to|need\s+to|really\s+need\s+to|should)\s+(?:tell|say|share|give|answer)\b"
    r"|\bi\s+need\s+you\s+to\s+(?:tell|share|give|say|answer)\b|\bjust\s+tell\s+me\b|\bcome\s+on\b"
    r"|\bdon'?t\s+be\s+shy\b|\bwhy\s+(?:not|won'?t\s+you|don'?t\s+you)\b|\bi\s+insist\b"
    r"|\bwithout\s+(?:it|that|this)\s+i\s+can'?t\b|\bplease\s+(?:just\s+)?(?:tell|share|answer)\s+(?:me|it)\b"
    r"|\bbatana\s+(?:hoga|zaroori|parega)\b|\bbatao\s+na\b|\bbas\s+bata\s+d(?:o|ein|en)\b|\bbata\s+d(?:ein|en)\s+na\b"
    r"|\bbataiye\s+na\b|\bzaroor\s+bata|\bbina\s+bataye\b|\bsharma(?:en|o)\s+nahi\b|\bkyun\s+nahi\s+bata"
    r"|بتانا\s+(?:ہوگا|ضروری|پڑے\s+گا)|بس\s+بتا\s+د(?:یں|و)|بتا\s+دیں\s+نا|شرمائیں\s+نہیں|کیوں\s+نہیں\s+بتا|بتائیں\s+تو\s+سہی"
    r"|يجب\s+أن\s+تخبرني|لازم\s+تقول|قل\s+لي\s+فقط|أصر|لماذا\s+لا\s+تقول|لا\s+تخجل"
    r"|बताना\s+(?:होगा|ज़रूरी|जरूरी|पड़ेगा)|बस\s+बता\s+दी(?:जिए|जिये|ए)|शरमाइए\s+मत|क्यों\s+नहीं\s+बता"
)
COMFORT = _rx(
    r"comfortable|no\s+pressure|if\s+you'?d\s+like|only\s+if|\bskip\b|\bjitna\b|jo\s+aap|مناسب|جتنا|جو\s+آپ|راحة|تشعر|يناسبك|जितना|जो\s+आप"
)


def _pressure(reply: str, context: dict[str, Any]) -> list[Finding]:
    if not HESITATES.search(_latest(context)):
        return []
    for sentence in _sentences(reply):
        if PRESSURES.search(sentence) and not COMFORT.search(sentence):
            return [
                (
                    "R-PRIV-08",
                    "they hesitated to share this: never press for it. Say they can share what they are "
                    "comfortable with, or move on to something else",
                    False,
                )
            ]
    return []


# --- R-VOICE-11: name things the way the person names them -------------------------------------
GENERIC_LABEL = (
    _rx(
        r"\b(?:location|branch|shop|store|outlet|site|warehouse|godown|unit|item|product|client|customer|employee|department|office|premises|dukaan|dukan|dukaanein)\s*#?\d{1,2}\b(?!\s*(?:%|am\b|pm\b|hours?|hrs?|days?|years?|months?|weeks?|minutes?|min\b|kg\b|pcs\b|pieces))"
    ),
    _rx(
        r"\b(?-i:Location|Branch|Shop|Store|Outlet|Site|Warehouse|Godown|Unit|Item|Product|Client|Customer|Employee|Department)\s+(?-i:[A-H])\b(?!['-]|\s*\.\w)",
        0,
    ),
    _rx(r"(?:دکان|برانچ|شاخہ|گودام|آؤٹ\s*لیٹ|کسٹمر|گاہک)\s*#?\d{1,2}(?!\d)"),
    _rx(
        r"(?:الفرع|فرع|الموقع|موقع|المتجر|متجر|المحل|محل|المستودع|العميل|عميل)\s*#?[\d٠-٩]{1,2}(?![\d٠-٩])"
    ),
    _rx(r"(?:दुकान|शाखा|ब्रांच|गोदाम|ग्राहक|स्थान)\s*#?[\d०-९]{1,2}(?![\d०-९])"),
)


def _their_names(reply: str, context: dict[str, Any]) -> list[Finding]:
    heard = _heard(context)
    for pattern in GENERIC_LABEL:
        for m in pattern.finditer(reply):
            label = " ".join(m.group(0).lower().split())
            if label in heard or label.replace(" ", "") in heard.replace(" ", ""):
                continue
            return [
                (
                    "R-VOICE-11",
                    f'"{m.group(0)}" is your label, not theirs: name it the way they do '
                    '("the Gulberg branch"), never "Location 2"',
                    False,
                )
            ]
    return []


# --- R-ASK-04: closed or choice questions for brief writers ------------------------------------
BRIEF_WORDS = 5
CHOICE = _rx(r"\bor\b|\bya\b|\bأم\b|\bأو\b|(?:^|\s)یا(?:\s|$)|(?:^|\s)या(?:\s|$)")
OPEN_QUESTION = _rx(
    r"^\W*(?:and\s+|so\s+)?(?:how(?!\s+(?:many|much|often|long|big|far|old|soon|late|early))|why|tell\s+me|describe|explain"
    r"|walk\s+me|(?:can|could|would)\s+you\s+(?:tell|describe|explain|walk)|what(?:'s|\s+is|\s+are)?\s+(?:going\s+on|happening|exactly|else|wrong)"
    r"|what\s+happens)"
    r"|^\W*(?:aur\s+)?(?:ye\s+|yeh\s+|isme\s+)?(?:kaise|kese|kaisay|kyun|kyon)\b|\btafseel\b|\bsamjhayen\b"
    r"|^\W*(?:یہ\s+|ایسا\s+)?(?:کیسے|کیوں)|^\W*(?:كيف|لماذا)(?:\s|$)|^\W*(?:यह\s+|ऐसा\s+)?(?:कैसे|क्यों)"
)


def _brief_writer_open_question(reply: str, context: dict[str, Any]) -> list[Finding]:
    latest = _latest(context)
    earlier = _customer_texts(context)
    if not latest or not earlier:
        return []
    if len(_tokens(latest)) > BRIEF_WORDS or len(_tokens(earlier[-1])) > BRIEF_WORDS:
        return []
    question = _last_question(reply)
    if question and not CHOICE.search(question) and OPEN_QUESTION.search(question):
        return [
            (
                "R-ASK-04",
                'they write briefly: ask a closed or choice question ("Every shop, or only some?"), '
                "not an open one",
                False,
            )
        ]
    return []


# --- R-ASK-05: a skipped or ignored question is not re-asked -----------------------------------
SKIPS = _rx(
    r"\bskip\b|\bpass\b|\bnext\b|\bidk\b|\bi\s+don'?t\s+know\b|\bdont\s+know\b|\bno\s+idea\b|\bnot\s+sure\b|\bcan'?t\s+say\b|\bmove\s+on\b|\bnever\s*mind\b"
    r"|\bpata\s+nahi\b|\bnahi\s+pata\b|\bmaloom\s+nahi\b|\bchhor\s+do\b|\bchodo\b|\bchor\s+do\b|\bagla\b"
    r"|پتہ\s+نہیں|پتا\s+نہیں|نہیں\s+پتہ|نہیں\s+پتا|معلوم\s+نہیں|چھوڑ"
    r"|لا\s+أعرف|لا\s+اعرف|مش\s+عارف|لا\s+أدري|تخطى|تجاوز"
    r"|पता\s+नहीं|नहीं\s+पता|छोड़|मालूम\s+नहीं"
)
CONFUSED = _rx(
    r"what\s+do\s+you\s+mean|don'?t\s+understand|do\s+not\s+understand|not\s+sure\s+what\s+you|\bhuh\b|\bpardon\b|come\s+again|say\s+that\s+again|\brepeat\b"
    r"|samajh\s+nahi|\bmatlab\b|dobara|phir\s+se\s+bol|سمجھ\s+نہیں|مطلب|دوبارہ|ماذا\s+تعني|لم\s+أفهم|لا\s+أفهم|समझ\s+नहीं|मतलब|दोबारा"
)
SHORT_ANSWER_WORDS = 3


def _reasks_a_skipped_question(reply: str, context: dict[str, Any]) -> list[Finding]:
    latest = _latest(context)
    mine = [_stems(s) for s in _sentences(reply) if _is_question(s)]
    questions = [_last_question(t) for t in _pi_texts(context)[-2:]]
    asked = [_stems(q) for q in questions if q]
    if not latest or not mine or not asked:
        return []
    skipped = bool(SKIPS.search(latest))
    if not skipped:
        if (
            CONFUSED.search(latest)
            or _is_question(latest)
            or len(_tokens(latest)) <= SHORT_ANSWER_WORDS
        ):
            return []  # a clarification, or a short answer to it
    threshold = 0.5 if skipped else 0.75
    for new in mine:
        for old in asked:
            if len(new) >= 3 and len(old) >= 3 and _overlap(new, old) >= threshold:
                return [
                    (
                        "R-ASK-05",
                        "they skipped or ignored that question: do not ask it again in other words, "
                        "mark it unknown and ask about something else",
                        False,
                    )
                ]
    return []


# --- R-CANT-01/02: a limit is said plainly first, then what happens next -----------------------
REFUSAL = _rx(
    r"\b(?:i|we|pi)\s*(?:can't|cannot|can\s+not|am\s+not\s+able\s+to|'m\s+not\s+able\s+to|am\s+unable\s+to|'m\s+unable\s+to)"
    r"|\b(?:i|we)\s+(?:don't|do\s+not)\s+(?:do|offer|provide|handle)\b|\b(?:workzap|pi)\s+(?:doesn't|does\s+not|can't|cannot)\b"
    r"|\bnot\s+something\s+(?:i|we)\s+can\b"
    r"|\b(?:main|mein|hum)\s+(?:\w+\s+){0,3}nahi\s+(?:kar|de|bata|dekh|sun)\s+sak(?:ta|ti|te)\b|\bworkzap\s+(?:ye\s+)?nahi\s+karta\b|\bmere\s+bas\s+mein\s+nahi\b"
    r"|(?:میں|ہم)\s+(?:\S+\s+){0,3}نہیں\s+(?:کر|دے|بتا|دیکھ)\s+سک(?:تا|تی|تے)"
    r"|(?<!\S)لا\s+(?:أستطيع|استطيع|يمكنني|أقدر|نستطيع|يمكننا)"
    r"|(?:मैं|हम)\s+(?:\S+\s+){0,3}नहीं\s+(?:कर|दे|बता|देख)\s+सक(?:ता|ती|ते)"
    r"|\bje\s+ne\s+peux\s+pas\b|\bnous\s+ne\s+pouvons\s+pas\b|\bno\s+puedo\b|\bno\s+podemos\b"
)
CONDITIONAL = _rx(r"\b(?:if|unless|when|whenever|agar|jab)\b|اگر|إذا|अगर|जब")
NEXT_STEP = _rx(
    r"\b(?:instead|what\s+i\s+can|i\s+can|i\s+will|i'll|let\s+me|we\s+can|you\s+can|happy\s+to|team|next|meanwhile|for\s+now|here(?:'s|\s+is))\b"
    r"|sak(?:ta|ti|te)\s+h(?:oon|un|ain)\b|\biske\s+bajaye\b|\baage\b|\babhi\b|\bagar\s+aap\b|\bmadad\b"
    r"|سک(?:تا|تی|تے)\s+ہ(?:وں|یں)|بجائے|ٹیم|آگے|اگر\s+آپ|مدد"
    r"|يمكنني|يمكننا|أستطيع|بدلاً|بدلا|فريق|التالي|ساعد"
    r"|सक(?:ता|ती|ते)\s+(?:हूँ|हूं|हैं|है)|बजाय|टीम|आगे|अगर\s+आप|मदद"
    r"|\bje\s+peux\b|à\s+la\s+place|équipe|nous\s+pouvons|\bpuedo\b|en\s+su\s+lugar|equipo|podemos"
)


OPENER_WORDS = 6  # "Thanks for asking about that.": a pleasantry before the limit, not a scope line


def _refusals(reply: str) -> list[int]:
    return [
        i
        for i, s in enumerate(_sentences(reply))
        if REFUSAL.search(s) and not CONDITIONAL.search(s) and not _is_question(s)
    ]


def _limits(reply: str) -> list[Finding]:
    found: list[Finding] = []
    sentences = _sentences(reply)
    refused = _refusals(reply)
    if not refused:
        return found
    openers = sentences[: refused[0]]
    if 0 not in refused and all(
        len(_tokens(x)) <= OPENER_WORDS and not _is_question(x) for x in openers
    ):
        found.append(
            (
                "R-CANT-01",
                'when you cannot help, say so plainly in the first sentence ("I can\'t do that."), '
                "before anything else",
                False,
            )
        )
    rest = REFUSAL.sub(" ", reply)
    if not any(_is_question(s) for s in sentences) and not NEXT_STEP.search(rest):
        found.append(
            (
                "R-CANT-02",
                "after a limit say what happens next or what you can do instead; never end on the "
                "refusal alone",
                False,
            )
        )
    return found


# --- X5: business distress without danger -------------------------------------------------------
DISTRESS = _rx(
    r"\bbankrupt\w*|\bgoing\s+under\b|\bshut(?:ting)?\s+down\b|\bclos(?:e|ing)\s+(?:down|(?:my|the|our)\s+(?:shop|business|store))\b"
    r"|\blos(?:e|ing)\s+(?:my|the|our)\s+(?:business|shop|store)\b|\bcan'?t\s+(?:pay|afford)\s+(?:the\s+|my\s+|our\s+)?(?:rent|salaries|wages|staff|bills|loan)\b"
    r"|\bbusiness\s+is\s+(?:dying|failing|collapsing|finished|dead)\b|\bdrowning\s+in\s+debt\b"
    r"|dewaliya|diwalia|diwaliya|business\s+doob|karobar\s+doob|tankhwa\s+nahi\s+de|dukaan\s+band\s+ho|business\s+khatam"
    r"|دیوالیہ|کاروبار\s+ڈوب|تنخواہ\s+نہیں|دکان\s+بند\s+ہو|إفلاس|افلاس|أفلس|أفلست|إغلاق\s+المحل|اغلاق\s+المحل"
    r"|दिवालिया|कारोबार\s+डूब|दुकान\s+बंद\s+हो|कर्ज\s+में\s+डूब"
)
DANGER = _rx(
    r"\bsuicid\w*|\bkill\s+myself\b|\bend\s+it\s+all\b|\bend\s+my\s+life\b|\bself[- ]harm\b|\bwant\s+to\s+die\b|\bdon'?t\s+want\s+to\s+live\b"
    r"|khudkushi|khud\s*kushi|mar\s+jana\s+chahta|mar\s+jaoon|خودکشی|مر\s+جاؤں|مرنا\s+چاہتا|انتحار|أقتل\s+نفسي|أريد\s+أن\s+أموت|आत्महत्या|मर\s+जाना\s+चाहता|मर\s+जाऊँ"
)
CRISIS_REDIRECT = _rx(
    r"\b(?:1122|999|911|112)\b|\b(?:helpline|hotline|crisis\s+line|emergency\s+(?:services|number)|someone\s+you\s+trust|ambulance)\b"
    r"|ایمرجنسی|ہیلپ\s*لائن|طوارئ|الإسعاف|आपातकालीन|हेल्पलाइन"
)
MONEY_ADVICE = _rx(
    r"\b(?:take|get|apply\s+for|try)\s+(?:a\s+|an\s+)?(?:bank\s+|business\s+|personal\s+)?loan\b|\b(?:declare|file\s+for)\s+(?:bankruptcy|insolvency)\b"
    r"|\bsell\s+(?:your\s+)?(?:assets|stock|shop|property|equipment)\b|\bborrow\b|\binvest\b|\brestructur\w+\b"
    r"|قرض\s+(?:لیں|لے)|दिवालिया\s+घोषित|कर्ज\s+लें|اقترض"
)
ACKNOWLEDGES = _rx(
    r"a\s+lot\s+to\s+carry|\bheavy\b|\bhard\b|\btough\b|\bdifficult\b|\bstress\w*|\bworr\w+|\bsorry\b|\bunderstand\b|\bmust\s+be\b|\bcarry\b|\bpainful\b|\bscary\b|\boverwhelm\w*"
    r"|mushkil|pareshan|afsos|\bdukh\b|tension|sakht|bhaari|bhari|samajh\s+sak|maazrat|\bmaaf"
    r"|مشکل|پریشان|افسوس|دکھ|بھاری|سمجھ\s+سکت|معذرت|ٹینشن|سخت"
    r"|آسف|صعب|متعب|أتفهم|اتفهم|ثقيل|مؤسف|قلق|ضغط|أفهم"
    r"|मुश्किल|परेशान|अफ़सोस|अफसोस|दुख|भारी|समझ\s+सक|क्षमा|तनाव|कठिन"
    r"|désolé|difficile|\bdur\b|comprends|lo\s+siento|difícil|\bduro\b|entiendo"
)


def _distress(reply: str, context: dict[str, Any]) -> list[Finding]:
    latest = _latest(context)
    if not DISTRESS.search(latest) or DANGER.search(latest):
        return []
    if _state(context) == flow.State.X_EMERGENCY:
        return []
    sentences = _sentences(reply)
    if CRISIS_REDIRECT.search(reply):
        why = "this is business distress, not an emergency: no emergency numbers or crisis redirect"
    elif MONEY_ADVICE.search(reply):
        why = "no financial advice for business distress: listen, do not tell them what to do with money"
    elif not ACKNOWLEDGES.search(" ".join(sentences[:2])):
        why = 'acknowledge it first, in a few words ("That\'s a lot to carry."), then note it as a problem'
    else:
        return []
    return [("X5", why, False)]


# --- R-PROM-02: pi never decides for the person ------------------------------------------------
DECIDES = _rx(
    r"\bi(?:'ve|\s+have)\s+decided\b|\bi(?:'ll|\s+will)\s+(?:decide|choose|pick)\b|\blet\s+me\s+decide\b"
    r"|\bmy\s+(?:recommendation|advice|suggestion|pick|choice|verdict)\s+is\b|\b(?:the\s+)?best\s+(?:option|choice|move|way)\s+(?:is|would\s+be)\s+to\b"
    r"|\bi(?:'d|\s+would)\s+(?:go\s+with|choose|pick)\b"
    r"|\byou\s+(?:need|have|must|ought)\s+to\s+(?:hire|fire|close|sell|stop|switch|choose|buy|cancel|replace|expand|quit|sack|shut)\b"
    r"|\bgo\s+with\s+(?:option|the\s+(?:first|second|third|cheaper))\b"
    r"|\bmera\s+mashwara\b|\bmeri\s+raye?\b|\bmain\s+ne\s+faisla\s+(?:kar\s+liya|kiya)\b"
    r"|\baap\s+ko\b[^.?!\n]{0,40}\b(?:nikal|band\s+kar|badal|bech|replace|chun)\w*\s+(?:dena|lena|karna)?\s*(?:chahiye|hoga|parega)\b"
    r"|میرا\s+مشورہ|میری\s+رائے\s+(?:میں|ہے)|میں\s+نے\s+فیصلہ\s+کر\s+لیا"
    r"|آپ\s+کو\b[^۔؟\n]{0,40}(?:نکال|بند\s+کر|بدل|بیچ)\S*\s+(?:دینا|لینا|کرنا)?\s*(?:چاہیے|ہوگا|پڑے\s+گا)"
    r"|نصيحتي|أنصحك|قررت|يجب\s+عليك\s+أن\s+(?:تبيع|تغلق|تطرد|تغير|تلغي|تشتري)"
    r"|मेरी\s+सलाह|मैंने\s+फैसला|मैंने\s+फ़ैसला"
    r"|आपको\b[^।?\n]{0,40}(?:निकाल|बंद\s+कर|बदल|बेच)\S*\s+(?:देना|लेना|करना)?\s*(?:चाहिए|होगा|पड़ेगा)"
)


def _decides(reply: str, context: dict[str, Any]) -> list[Finding]:
    heard = _heard(context)
    for m in DECIDES.finditer(reply):
        if m.group(0).lower() in heard:
            continue
        return [
            (
                "R-PROM-02",
                "never decide for them: lay out what you noted and let them choose",
                False,
            )
        ]
    return []


# --- R-PROM-03: no forecasts of the person's business ------------------------------------------
FORECASTS = (
    (
        _rx(
            r"\b(?:sales|revenue|profits?|business|customers|orders|income|costs|expenses|demand|footfall|growth|turnover|margins?|prices)\s+"
            r"(?:will|are\s+going\s+to|is\s+going\s+to|are\s+bound\s+to|is\s+bound\s+to)\s+(?:\w+\s+){0,2}"
            r"(?:rise|go\s+up|go\s+down|drop|fall|decline|grow|increase|improve|double|recover|collapse|suffer|shrink|climb|jump|pick\s+up|crash|boom|take\s+off|fail|survive)\b"
        ),
        None,
    ),
    (
        _rx(
            r"\byou(?:'ll|\s+will|\s+are\s+going\s+to)\s+(?:be\s+(?:profitable|rich|broke|out\s+of\s+business|bankrupt|successful)"
            r"|make\s+(?:more|a\s+profit|money)|lose\s+(?:money|customers|clients|sales)|grow|expand|struggle|go\s+(?:broke|bankrupt))\b"
        ),
        None,
    ),
    (
        _rx(
            r"\b(?:sale|sales|munafa|profit|business|customers?|orders?|income|aamdani|demand|kharcha|karobar)\s+(?:\w+\s+){0,2}"
            r"(?:barh|badh|ghat|gir|doob|dub|behtar)\w*(?:\s+(?:jay|ho\s+jay)\w*)?"
        ),
        _rx(r"eg[ia]|enge|jay|ga\b|gi\b|ge\b"),
    ),
    (
        _rx(
            r"(?:فروخت|سیلز|منافع|کاروبار|آمدنی|گاہک|طلب)\s+(?:\S+\s+){0,2}(?:بڑھ|گھٹ|گر|ڈوب)\S*(?:\s+(?:جائے|جائیں|گی|گا|گے))*"
        ),
        _rx(r"(?:^|\s)\S*(?:گی|گا|گے)(?:$|\s)"),
    ),
    (
        _rx(
            r"(?:المبيعات|الأرباح|الارباح|الإيرادات|الأعمال|العملاء|الطلبات|الدخل|مبيعاتك|أرباحك)\s+(?:\S+\s+)?"
            r"(?:ستزداد|ستنخفض|سترتفع|ستتحسن|ستنمو|ستنهار|ستتراجع|ستقل|سيزداد|سينخفض|سيرتفع|سيتحسن|سينمو|سينهار)"
        ),
        None,
    ),
    (
        _rx(
            r"(?:बिक्री|मुनाफा|मुनाफ़ा|कारोबार|व्यापार|आमदनी|ग्राहक|ऑर्डर|मांग)\s+(?:\S+\s+){0,2}"
            r"(?:बढ़ेगी|बढ़ेगा|बढ़ेंगे|घटेगी|घटेगा|गिरेगी|गिरेगा|डूबेगा|डूबेगी|सुधरेगी|सुधरेगा)"
        ),
        None,
    ),
)


def _forecasts(reply: str, context: dict[str, Any]) -> list[Finding]:
    heard = _heard(context)
    for sentence in _sentences(reply):
        if _is_question(sentence) or CONDITIONAL.search(sentence):
            continue
        for pattern, future in FORECASTS:
            for m in pattern.finditer(sentence):
                if future is not None and not future.search(m.group(0)):
                    continue
                if m.group(0).lower() in heard:
                    continue
                return [
                    (
                        "R-PROM-03",
                        f'never forecast their business ("{m.group(0)}"): say what you noted, not what will happen',
                        True,
                    )
                ]
    return []


# --- R-SOL-09: no regulated advice, even with ideas --------------------------------------------
def _directive(verbs: str) -> re.Pattern[str]:
    """A verb used as an instruction: the sentence opens with it ("Apply urea twice") or says "you
    can/should/need to ..." before it. A sentence that only mentions the verb ("List every claim
    and deduction") is not advice."""
    return _rx(
        rf"^\W*(?:(?:please|then|also|and|just|so|first|next)\s+)?(?:{verbs})\b"
        rf"|\byou(?:'ll|\s+(?:can|should|could|may|must|need\s+to|will|ought\s+to))\s+(?:\w+\s+){{0,2}}(?:{verbs})\b"
    )


ADVICE_DOMAINS: tuple[tuple[re.Pattern[str], re.Pattern[str]], ...] = (
    # veterinary
    (
        _rx(
            r"\b(?:antibiotics?|dewormers?|vaccin(?:e|es|ate|ation)s?|steroids?|hormone\s+injections?|foot[- ]and[- ]mouth|withdrawal\s+period|drench\w*)\b"
        ),
        _directive(r"give|inject|administer|dose|treat|start|try|switch\s+to"),
    ),
    # agronomy
    (
        _rx(
            r"\b(?:urea|dap|npk|fertili[sz]ers?|pesticides?|insecticides?|herbicides?|fungicides?|seed\s+rate|sowing\s+(?:date|time)|irrigat\w+|crop\s+rotation|feed\s+ration)\b"
        ),
        _directive(r"apply|spray|sow|plant|irrigate|increase|reduce|dose|mix"),
    ),
    # tax
    (
        _rx(r"\b(?:tax|vat|gst|ntn|withholding|deductions?)\b"),
        _directive(
            r"claim|deduct|write\s+off|declare|file|register\s+for|pay\s+less|avoid|reduce\s+your|evade|minimi[sz]e"
        ),
    ),
    # financial
    (
        _rx(
            r"\b(?:refinanc\w+|mutual\s+funds?|overdrafts?|credit\s+lines?|bonds?|fixed\s+deposits?|savings\s+accounts?|interest\s+rates?|crypto\w*|forex)\b"
        ),
        _directive(
            r"take|get|open|buy|sell|invest|move|put|switch|negotiate|choose|try|apply|renew|refinanc\w+"
        ),
    ),
    # medical
    (
        _rx(
            r"\b(?:paracetamol|panadol|ibuprofen|painkillers?|insulin|antibiotics?|dosage|\d+\s?(?:mg|mcg|ml))\b"
        ),
        _directive(r"take|give|try|start|stop|prescribe|drink"),
    ),
    # legal
    (
        _rx(
            r"\b(?:sue|lawsuit|legal\s+notice|take\s+(?:them|him|her|the\s+\w+)\s+to\s+court|void\s+the\s+contract|terminate\s+the\s+contract)\b"
        ),
        _rx(r"\byou\s+(?:can|should|could|may|must|need\s+to)\b"),
    ),
    # Roman Urdu
    (
        _rx(r"\b(?:urea|khaad|antibiotic|teeka|spray)\b"),
        _rx(r"\b(?:dalen|dalein|daalein|lagayen|lagayein|chhirken|dein)\b"),
    ),
    (_rx(r"\bdawai\b"), _rx(r"\b(?:khayen|khaiye|piyen)\b")),
    (
        _rx(
            r"\btax\s+(?:bachayen|kam\s+karein|nahi\s+dein|file\s+karein)\b|\bloan\s+(?:lein|le\s+lein|len)\b"
        ),
        _rx(r"."),
    ),
    # Urdu, Arabic, Hindi
    (
        _rx(r"یوریا|کھاد|سپرے|ٹیکہ|ویکسین|اینٹی\s*بائیوٹک"),
        _rx(r"ڈالیں|ڈال\s+دیں|لگائیں|چھڑکیں|پلائیں"),
    ),
    (
        _rx(r"اليوريا|يوريا|سماد|مبيد|لقاح|مضاد\s+حيوي|باراسيتامول"),
        _rx(r"(?<!\S)(?:ضع|أضف|ارش|رش|أعط|اعط|خذ)(?!\S)"),
    ),
    (
        _rx(r"यूरिया|खाद|कीटनाशक|टीका|वैक्सीन|एंटीबायोटिक|पैरासिटामोल"),
        _rx(r"डालें|डाल\s+दें|लगाएं|लगाएँ|छिड़कें|पिलाएं|खाएं"),
    ),
)


def _regulated_advice(reply: str, context: dict[str, Any]) -> list[Finding]:
    heard = _heard(context)
    for sentence in _sentences(reply):
        if _is_question(sentence):
            continue
        for noun, lead in ADVICE_DOMAINS:
            m = noun.search(sentence)
            if m and lead.search(sentence) and m.group(0).lower() not in heard:
                return [
                    (
                        "R-SOL-09",
                        f'no legal, tax, medical, financial, veterinary or agronomy advice ("{m.group(0)}"): '
                        "keep ideas operational",
                        True,
                    )
                ]
    return []


# --- R-ANS-02: a yes/no question gets the yes or the no first ----------------------------------
YES_NO_ASKED = (
    _rx(
        r"^\W*(?:can|could|will|would|do|does|did|is|are|am|have|has|should|may)\s+(?:you|u|pi|it|this|workzap|your|we)\b[^?]*\?\s*$"
    ),
    _rx(r"^\W*kya\s+(?:aap|ye|yeh|workzap|pi|tum)\b[^?]*\?\s*$"),
    _rx(r"\bya\s+nahi\s*\?\s*$"),
    _rx(r"^\W*کیا\s+(?:آپ|یہ|ورک\s*زیپ|تم)\b[^؟?]*[؟?]\s*$"),
    _rx(r"^\W*هل\s+[^؟?]*[؟?]\s*$"),
    _rx(r"^\W*क्या\s+(?:आप|यह|ये|तुम)\b[^?]*\?\s*$"),
    _rx(r"^\W*(?:pouvez|savez|est-ce\s+que|peut-on|faites)\b[^?]*\?\s*$"),
    _rx(r"^\W*¿(?:puede|puedes|pueden|tiene|tienen|hacen|se\s+puede)\b[^?]*\?\s*$"),
)
YES_NO_EXPLICIT = _rx(r"\bya\s+nahi\b")
POLARITY_TOKENS = frozenset(
    unicodedata.normalize("NFC", w)
    for w in (
        "yes yeah yep yup sure certainly absolutely definitely no nope not never can can't cannot could couldn't will won't "
        "would wouldn't do don't does doesn't did didn't it's we're i'm "
        "haan han nahi nahin nai bilkul zaroor jee ji "
        "ہاں نہیں بالکل ضرور جی نہ "
        "نعم أجل بالتأكيد طبعاً طبعا بالطبع بلى لا ليس يمكن يمكنني يمكننا نستطيع أستطيع أقدر نقدر ممكن "
        "हाँ हां जी नहीं बिल्कुल ज़रूर जरूर "
        "oui non certainement pas peux peut pouvons sí si no claro puedo podemos puede tampoco"
    ).split()
)
POLARITY_PHRASES = tuple(
    unicodedata.normalize("NFC", p)
    for p in (
        "of course",
        "we do",
        "i do",
        "it is",
        "it does",
        "it isn't",
        "that is",
        "they are",
        "we are",
        "i am",
        "there is",
        "there are",
        "kar sakte",
        "kar sakta",
        "kar sakti",
        "sakte hain",
        "sakta hai",
        "sakti hai",
        "ho sakta",
        "karta hai",
        "karti hai",
        "karte hain",
        "سکتے ہیں",
        "سکتا ہوں",
        "سکتی ہوں",
        "ہو سکتا",
        "کر سکتے",
        "کرتے ہیں",
        "کرتا ہے",
        "کرتی ہے",
        "सकते हैं",
        "सकता हूँ",
        "सकता हूं",
        "सकती हूँ",
        "सकती हूं",
        "हो सकता",
        "करते हैं",
        "करता है",
        "bien sûr",
        "por supuesto",
    )
)


def _asked_yes_no(latest: str) -> bool:
    last = (_sentences(latest) or [""])[-1]
    if YES_NO_EXPLICIT.search(last):
        return True
    return any(p.search(last) for p in YES_NO_ASKED) and not CHOICE.search(last)


def _answers_yes_no(reply: str, context: dict[str, Any]) -> list[Finding]:
    latest = _latest(context)
    first = (_sentences(reply) or [""])[0]
    if not latest or not first or not _asked_yes_no(latest):
        return []
    words = _tokens(first)
    padded = " " + " ".join(words) + " "
    if any(w in POLARITY_TOKENS for w in words) or any(
        f" {p} " in padded for p in POLARITY_PHRASES
    ):
        return []
    return [
        (
            "R-ANS-02",
            "they asked a yes/no question: the first sentence is the yes or the no, then the detail",
            False,
        )
    ]


# --- R-ECHO-01: one noted line per problem ------------------------------------------------------
NOTED_LINE = _rx(
    r"(?:i(?:'ve|\s+have)\s+noted(?:\s+it)?|noted|note\s+kar\s+liya"
    + langs.NOTED_FRAME
    + r")\s*[:：]\s*([^.?!\n۔؟।]+)"
)
CORRECTING = _rx(
    r"\bi\s+meant\b|\bactually\b|\bcorrect(?:ion)?\b|\bgalat\b|mera\s+matlab|أقصد|मेरा\s+मतलब"
)


def _noted_twice(reply: str, context: dict[str, Any]) -> list[Finding]:
    if context.get("said_wrong") or CORRECTING.search(_latest(context)):
        return []
    mine = [_stems(t) for t in NOTED_LINE.findall(reply)]
    if not mine:
        return []
    before = [_stems(t) for text in _pi_texts(context) for t in NOTED_LINE.findall(text)]
    for new in mine:
        for old in before:
            if len(new) >= 2 and len(old) >= 2 and _overlap(new, old) >= 0.6:
                return [
                    (
                        "R-ECHO-01",
                        "you already noted this problem: confirm a problem once only, do not note it again",
                        False,
                    )
                ]
    return []


# --- R-ECHO-02: bulleted restatements only in the summary ---------------------------------------
BULLET_MIN_STEMS = 3
RESTATES_OLD = 0.7


def _bullets_restate(reply: str, context: dict[str, Any]) -> list[Finding]:
    if _state(context) == flow.State.S4_SORTED_SUMMARY:
        return []
    points = [_stems(x.lstrip()[2:]) for x in reply.splitlines() if x.lstrip().startswith(BULLETS)]
    older: set[str] = set()
    for text in _customer_texts(context):
        older |= _stems(text)
    latest = _stems(_latest(context))
    if len(points) < 2 or not older:
        return []
    old_points = [
        p
        for p in points
        if len(p) >= BULLET_MIN_STEMS
        and len(p & older) / len(p) >= RESTATES_OLD
        and len(p & latest) / len(p) < 0.5
    ]
    if len(old_points) >= 2:
        return [
            (
                "R-ECHO-02",
                "do not list back what they said earlier: bullets restate only in the summary, or for "
                "new problems in their latest message",
                False,
            )
        ]
    return []


# --- R-ASK-03 / R-MEM-02: never ask what they already said -------------------------------------
NUMBER_WORDS = frozenset(
    unicodedata.normalize("NFC", w)
    for w in (
        "one two three four five six seven eight nine ten eleven twelve ek do teen char chaar paanch panch chhe che saat aath nau das "
        "ایک دو تین چار پانچ چھ سات آٹھ نو دس واحد اثنان ثلاثة أربعة خمسة ستة سبعة ثمانية تسعة عشرة एक दो तीन चार पांच पाँच छह सात आठ नौ दस"
    ).split()
)
COUNT_MARKERS = (
    ("how", "many"),
    ("kitne",),
    ("kitni",),
    ("كم",),
    ("कितने",),
    ("कितनी",),
    ("کتنے",),
    ("کتنی",),
)
CONFIRMING = _rx(r"\bright\b|\bcorrect\b|\bsahi\b|\btheek\b|صحيح|صحیح|ٹھیک|सही")
CONTAINED_MIN = 5


def _count_noun(question: str) -> str:
    words = _tokens(question)
    for marker in COUNT_MARKERS:
        n = len(marker)
        for i in range(len(words) - n):
            if tuple(words[i : i + n]) == marker:
                return words[i + n]
    return ""


def _has_number_next_to(noun: str, said: list[str]) -> bool:
    for i, w in enumerate(said):
        if not _same(w, noun):
            continue
        near = said[max(0, i - 2) : i] + said[i + 1 : i + 2]
        if any(x.isdigit() or x in NUMBER_WORDS for x in near):
            return True
    return False


def _asks_what_they_said(reply: str, context: dict[str, Any]) -> list[Finding]:
    said = _tokens(_heard(context))
    heard_stems = _stems(" ".join(said))
    for sentence in _sentences(reply):
        if not _is_question(sentence):
            continue
        noun = _count_noun(sentence)
        contained = _stems(sentence)
        if (noun and _has_number_next_to(noun, said)) or (
            len(contained) >= CONTAINED_MIN
            and contained <= heard_stems
            and not CONFIRMING.search(sentence)
        ):
            return [
                (
                    "R-ASK-03",
                    "they already told you this: do not ask it again, ask what is still unknown",
                    False,
                )
            ]
    return []


EXTRA_FIELDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "channels",
        _rx(
            r"\bwhere\s+do\s+you\s+(?:sell|get\s+(?:your\s+)?orders)\b|\bwhich\s+channels?\b|\baap\s+kahan\s+(?:bechte|bechti|sell)|\bkahan\s+bechte\s+hain\b|\bkis\s+channel\b|آپ\s+کہاں\s+بیچ|کہاں\s+بیچتے|أين\s+تبيع|اين\s+تبيع|आप\s+कहाँ\s+बेचते|आप\s+कहां\s+बेचते|किस\s+चैनल"
        ),
    ),
    (
        "website",
        _rx(
            r"\bwhat(?:'s|\s+is)\s+your\s+(?:website|web\s?site|site\s+url)\b|\bdo\s+you\s+have\s+a\s+(?:website|web\s?site)\b|\baap\s*ki\s+website\b|آپ\s+کی\s+ویب\s*سائٹ|ما\s+(?:هو\s+)?موقعك|هل\s+لديك\s+موقع|आपकी\s+वेबसाइट"
        ),
    ),
    (
        "goal",
        _rx(
            r"\bwhat\s+do\s+you\s+want\s+to\s+(?:achieve|get\s+out\s+of)\b|\bwhat(?:'s|\s+is)\s+your\s+(?:goal|aim)\b|\bwhat\s+are\s+you\s+(?:hoping|looking)\s+(?:to|for)\b|\baap\s+kya\s+(?:hasil|chahte)|\baap\s+ka\s+maqsad\b|آپ\s+کیا\s+(?:حاصل|چاہتے)|آپ\s+کا\s+مقصد|ما\s+(?:هو\s+)?هدفك|ماذا\s+تريد\s+أن\s+تحقق|आप\s+क्या\s+(?:हासिल|चाहते)|आपका\s+लक्ष्य"
        ),
    ),
    ("name", _rx(r"آپ\s+کا\s+نام|ما\s+(?:هو\s+)?اسمك|بمن\s+أتحدث|आपका\s+नाम|आप\s+का\s+नाम")),
    (
        "business_name",
        _rx(
            r"(?:کاروبار|دکان|کمپنی)\s+کا\s+نام|ما\s+(?:هو\s+)?اسم\s+(?:متجرك|شركتك|عملك|نشاطك(?:\s+التجاري)?|مشروعك)|(?:कारोबार|दुकान|कंपनी|बिज़नेस|बिजनेस)\s+का\s+नाम"
        ),
    ),
    (
        "business_type",
        _rx(
            r"کس\s+قسم\s+کا\s+(?:کاروبار|کام)|آپ\s+کا\s+کاروبار\s+کیا\s+(?:ہے|کرتا)|ما\s+نوع\s+(?:عملك|نشاطك|تجارتك|مشروعك)|ما\s+مجال\s+عملك|किस\s+तरह\s+का\s+(?:कारोबार|बिज़नेस|काम)|आपका\s+(?:कारोबार|बिज़नेस)\s+क्या"
        ),
    ),
    (
        "location",
        _rx(
            r"کس\s+شہر|آپ\s+کہاں\s+(?:ہیں|رہتے|واقع)|في\s+أي\s+(?:مدينة|بلد)|أين\s+(?:تقع|أنت)|किस\s+शहर|आप\s+कहाँ\s+(?:हैं|रहते)|आप\s+कहां"
        ),
    ),
    ("role", _rx(r"آپ\s+کا\s+(?:کردار|عہدہ)|ما\s+(?:هو\s+)?(?:دورك|منصبك)|आपकी\s+भूमिका|आपका\s+पद")),
    (
        "team_size",
        _rx(
            r"کتنے\s+(?:ملازم|اسٹاف|لوگ|کارکن)\s+(?:ہیں|ہوں)|كم\s+(?:عدد\s+)?(?:موظف|عامل)|कितने\s+(?:कर्मचारी|स्टाफ|लोग|कारीगर)"
        ),
    ),
    (
        "current_tools",
        _rx(
            r"کون\s+سا\s+(?:سافٹ\s*ویئر|سسٹم|ایپ)\s+(?:استعمال|use)|أي\s+(?:برنامج|نظام|تطبيق)\s+تستخدم|कौन\s+सा\s+(?:सॉफ्टवेयर|सिस्टम|ऐप)\s+(?:इस्तेमाल|use)"
        ),
    ),
)
PLACEHOLDER = _rx(r"^(whatsapp|customer|unknown|n/?a|none)\b|^\+?\d[\d ]+$")


def _asks_a_known_fact(reply: str, context: dict[str, Any]) -> list[Finding]:
    profile = context.get("customer_profile")
    profile = profile if isinstance(profile, dict) else {}
    block = context.get("what_i_know")
    block = block if isinstance(block, dict) else {}
    for sentence in _sentences(reply):
        if not _is_question(sentence):
            continue
        for field, pattern in EXTRA_FIELDS:
            known = _n(profile.get(field) or block.get(field)).strip()
            if known and not PLACEHOLDER.search(known) and pattern.search(sentence):
                return [
                    (
                        "R-MEM-02",
                        f'they already told you their {field.replace("_", " ")} ("{known}"): do not ask '
                        "again, use what you already know",
                        False,
                    )
                ]
    return []


CHECKS = (
    _pressure,
    _their_names,
    _brief_writer_open_question,
    _reasks_a_skipped_question,
    _asks_what_they_said,
    _asks_a_known_fact,
    _decides,
    _forecasts,
    _regulated_advice,
    _answers_yes_no,
    _noted_twice,
    _bullets_restate,
    _distress,
)


def check(reply: str, context: dict[str, Any]) -> list[Finding]:
    """Every gap rule the draft breaks, as (rule, message, hard). Empty when it is fine to send."""
    text = _n(reply)
    if not text.strip():
        return []
    found: list[Finding] = []
    for run in CHECKS:
        found.extend(run(text, context))
    found.extend(_limits(text))
    return found
