# ruff: noqa: E501  (the word lists read better one signal per line)
"""The four live dials of a conversation (Engagement Engine, Book 5, Part 2.2 to 2.4).

Openness (0 closed .. 4 volunteering), pace (slow .. fast), mode (Listen, Think, Fix, Buy) and the
trust trend (falling, flat, rising). They describe the conversation, never the person, and are
re-estimated after every message from signals in the latest words, by rules, not by a model.

Smoothing: a dial moves one notch at a time; a jump (a strong signal such as a sensitive disclosure
in a long message, or the owner saying "the real problem is...") may move openness two. A signal
beats a dial: when the words say Fix, the mode is Fix whatever it was.

Nothing here is stored. `estimate` replays the customer's messages, so the dials of the current
conversation can be recomputed at any time and no label about the person ever exists (spec 2.5).
Postures are names for the engine only (`posture`), never memory.
"""

import re
from dataclasses import dataclass, replace
from enum import IntEnum, StrEnum

from app.modules.pi import language

OPENNESS_MAX = 4
RETURN_GAP_HOURS = 24  # a return after this long is a trust signal
LONG_MESSAGE_WORDS = 12  # "a long message" for the openness signal


class Mode(StrEnum):
    LISTEN = "listen"  # wants to be heard
    THINK = "think"  # wants help understanding
    FIX = "fix"  # wants ideas now
    BUY = "buy"  # wants a document or a price


class Pace(IntEnum):
    SLOW = 0
    NORMAL = 1
    FAST = 2


class Trust(IntEnum):
    FALLING = -1
    FLAT = 0
    RISING = 1


def _words(*groups: str) -> re.Pattern[str]:
    """One alternation over several languages, matched on whole words in any script."""
    terms = [t.strip() for g in groups for t in g.split("|") if t.strip()]
    terms.sort(key=len, reverse=True)
    body = "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in terms)
    return re.compile(rf"(?<!\w)(?:{body})(?!\w)", re.IGNORECASE)


# Feeling words (Listen mode, openness up).
FEELING = _words(
    "worried|stressed|stress|tired|exhausted|struggling|overwhelmed|frustrated|fed up|scared|anxious|so hard|very hard|really hard|sleepless",
    "pareshan|pareshaan|thak gaya|thak gayi|thak gaye|thak gya|thak gyi|bohat mushkil|bahut mushkil|boht mushkil|bohat bura|bahut bura|tang aa gaya|tang aa gayi|dil dukhta|tension",
    "پریشان|تھک گیا|تھک گئی|تھک گئے|بہت مشکل|بہت برا|تنگ",
    "परेशान|थक गया|थक गई|बहुत मुश्किल|बहुत बुरा|तंग",
    "متعب|مرهق|تعبان|قلق|قلقان|صعب جدا|صعب جداً|متضايق|محبط",
    "fatigué|fatiguée|épuisé|épuisée|stressé|stressée|inquiet|inquiète|découragé|galère|très difficile|à bout",
    "خسته|نگران|خیلی سخت|ناراحت|کلافه|استرس",
    "cansado|cansada|agotado|agotada|estresado|estresada|preocupado|preocupada|agobiado|agobiada|muy difícil|muy dificil|harto|harta",
)

# Sensitive subjects: cash trouble, staff trust, family business, debt.
SENSITIVE = _words(
    "cash flow|cashflow|cash crunch|can't pay|cannot pay|unpaid|salaries|salary|payroll|debt|debts|loan|loans|owe|stealing|theft|steal|trust my staff|family business|my partner|my brother|my father|my husband|bankrupt",
    "udhaar|udhar|qarz|karz|salary|tankhwah|paisa phans|paisa phansa|cash ki tangi|tangi|chori|bharosa|khandani|family business|bhai ke saath|walid sahab|shareek|partner",
    "ادھار|قرض|تنخواہ|چوری|بھروسہ|خاندانی|شریک",
    "उधार|कर्ज|वेतन|तनख्वाह|चोरी|भरोसा|खानदानी|साझेदार",
    "دين|ديون|الديون|الدين|قرض|رواتب|الرواتب|راتب|الراتب|سرقة|سرقه|ثقة|شركة عائلية|شريكي|إفلاس",
    "dettes|dette|salaires|salaire|trésorerie|tresorerie|vol|confiance|entreprise familiale|mon associé|mon associe|faillite|emprunt",
    "قرض|بدهی|حقوق|دزدی|اعتماد|کسب و کار خانوادگی|شریک|ورشکست",
    "deuda|deudas|salarios|sueldos|sueldo|flujo de caja|robo|robando|confianza|negocio familiar|mi socio|quiebra|préstamo|prestamo",
)

# Hurry (pace fast, mode Fix or Buy).
HURRY = _words(
    "quickly|asap|hurry|in a hurry|right now|just tell me|get to the point|straight answer|how long will|how soon|be quick|come on",
    "jaldi|jldi|jaldi se|foran|seedha batao|seedha bataiye|sidha batao|kab tak|kab tk|jaldi batao|der ho rahi",
    "جلدی|فوراً|فورا|سیدھا بتائیں|سیدھا بتاؤ|کب تک",
    "जल्दी|फौरन|सीधा बताओ|कब तक",
    "بسرعة|عاجل|مستعجل|مباشرة|متى|بسرعه",
    "vite|rapidement|urgent|dites-moi directement|combien de temps|dépêchez|depechez|au plus vite",
    "زود|سریع|فوری|مستقیم بگو|کی میشه|کی می شه|عجله",
    "rápido|rapido|urgente|dime directamente|cuánto tarda|cuanto tarda|ya mismo|cuanto antes|apúrate|apurate",
)

# Fix: wants ideas now.
FIX = _words(
    "solution|solutions|what can we do|what can i do|any ideas|give me ideas|suggest|suggestions|what should i do|how do i fix|how to fix|fix this",
    "solution dein|solution do|solution den|solution dein ap|hal batao|hal bataen|hal bataiye|kya kar sakte hain|kya kar sakte hn|kya karna chahiye|idea dein|idea do|kuch karo|ap solution",
    "حل بتائیں|حل بتاو|حل دیں|کیا کر سکتے ہیں|کیا کریں|آئیڈیا دیں",
    "समाधान दो|समाधान बताओ|क्या कर सकते हैं|क्या करें|उपाय बताओ",
    "حل|ماذا نفعل|ماذا أفعل|اقتراح|اقتراحات|ما العمل",
    "solution|solutions|que faire|que peut-on faire|que puis-je faire|des idées|une idée|proposez",
    "راه حل|چه کار کنیم|چه کنم|پیشنهاد بده|ایده بده|چکار کنم",
    "solución|solucion|soluciones|qué podemos hacer|que podemos hacer|qué hago|que hago|ideas|sugiere|sugerencias",
)

# Buy: wants a document or a price.
BUY = _words(
    "how much|quote|quotation|price|pricing|cost of|how do we start|how do i start|how to start|proposal|get started|sign up|invoice",
    "kitna lagega|kitna lagay ga|kitna lage ga|kitna kharcha|kitne ka|quote|quotation|qeemat kitni|rate kya|kaise shuru karein|kaise shuru karen|kaise start|shuru kaise|kab shuru",
    "کتنا لگے گا|کتنا خرچ|کوٹیشن|قیمت کتنی|کیسے شروع کریں|شروع کیسے",
    "कितना लगेगा|कितना खर्चा|कोटेशन|कीमत कितनी|कैसे शुरू करें|शुरू कैसे",
    "كم التكلفة|كم السعر|عرض سعر|بكم|كيف نبدأ|كيف أبدأ|كم تكلف",
    "combien ça coûte|combien ca coute|combien cela coûte|devis|tarif|tarifs|prix|comment commencer|comment démarrer",
    "قیمت|چقدر میشه|چقدر می شه|پیشنهاد قیمت|چطور شروع کنیم|چگونه شروع کنیم|هزینه",
    "cuánto cuesta|cuanto cuesta|cuánto cobran|cuanto cobran|presupuesto|cotización|cotizacion|precio|precios|cómo empezamos|como empezamos|cómo empiezo|como empiezo",
)

# Think and trust test: who are you, how does this work.
TRUST_TEST = _words(
    "who are you|what are you|how does this work|how do you work|are you human|are you a bot|are you real|is this a bot|who is this",
    "aap kaun ho|ap kaun ho|aap kon ho|ap kon ho|tum kaun ho|ye kaise kaam karta hai|ye kese kaam karta hai|yeh kaise kaam karta hai|aap kya ho|ap kya ho|aap insaan ho|ap insan ho",
    "آپ کون ہیں|آپ کون ہو|یہ کیسے کام کرتا ہے|یہ کیسے کام کرتی ہے|آپ انسان ہیں",
    "आप कौन हो|आप कौन हैं|ये कैसे काम करता है|यह कैसे काम करता है|आप इंसान हैं",
    "من أنت|من انت|كيف يعمل|كيف تعمل|هل أنت إنسان|هل انت انسان|هل أنت روبوت",
    "qui êtes-vous|qui etes-vous|qui es-tu|comment ça marche|comment ca marche|êtes-vous un humain|etes-vous un robot|vous êtes un robot",
    "شما کی هستید|تو کی هستی|چطور کار می کنه|چطور کار میکنه|شما آدم هستید|ربات هستید",
    "quién eres|quien eres|quién es usted|quien es usted|cómo funciona|como funciona|eres humano|eres un robot|eres una persona",
)

# Correction: "no, not like that".
CORRECTION = _words(
    "no that's not|no, that's not|that's not what i|that is not what i|that's wrong|that is wrong|not what i said|not what i meant|you got it wrong|you misunderstood|that's not right|no not like that",
    "nahi aisa nahi|nahi, aisa nahi|nahi aisa nahin|aisa nahi hai|aisa nahi kaha|ye galat hai|yeh galat hai|ye jorr galat hai|ye jor galat hai|galat samjhe|aap ne galat samjha|ap ne ghalat samjha|ye nahi kaha|maine ye nahi kaha",
    "نہیں ایسا نہیں|ایسا نہیں ہے|یہ غلط ہے|آپ نے غلط سمجھا|میں نے یہ نہیں کہا",
    "नहीं ऐसा नहीं|ऐसा नहीं है|यह गलत है|ये गलत है|आपने गलत समझा|मैंने ये नहीं कहा",
    "لا ليس هكذا|ليس هذا ما قلت|هذا خطأ|هذا غلط|لم أقل هذا|أنت فهمت خطأ",
    "non, pas ça|non pas ça|ce n'est pas ça|ce n'est pas ce que j'ai dit|c'est faux|vous avez mal compris|ce n'est pas exact",
    "نه اینطور نیست|نه این طور نیست|این اشتباه است|اشتباه فهمیدی|این را نگفتم|اشتباه فهمیدید",
    "no, así no|no asi no|eso no es|eso no es lo que dije|está mal|esta mal|no es así|no es asi|entendiste mal|no dije eso",
)

# The owner moves the conversation: "the real problem is..." (treated as a jump, spec 2.4).
REAL_PROBLEM = _words(
    "the real problem is|the real issue is|actually the problem is|the main problem is",
    "asal masla ye hai|asal masla yeh hai|asli masla ye hai|asal baat ye hai",
    "اصل مسئلہ یہ ہے|اصل مسئلہ",
    "असल मसला ये है|असली समस्या ये है",
    "المشكلة الحقيقية|المشكلة الأساسية",
    "le vrai problème|le vrai probleme|le problème principal",
    "مشکل اصلی|مشکل واقعی",
    "el verdadero problema|el problema real|el problema principal",
)

# Asks pi's opinion: openness up, Think.
OPINION = _words(
    "what do you think|what's your view|what is your view|your opinion|do you think|what would you do",
    "aap kya kehte hain|ap kya kehte hain|aap ka kya khayal hai|ap ka kya khayal hai|aap kya sochte hain|aap ki kya raye|ap ki kya raye|aap kya kahenge",
    "آپ کا کیا خیال ہے|آپ کیا کہتے ہیں|آپ کی کیا رائے",
    "आपका क्या ख्याल है|आप क्या कहते हैं|आपकी क्या राय",
    "ما رأيك|ما رايك|ماذا تعتقد|ما تقييمك",
    "qu'en pensez-vous|quel est votre avis|que pensez-vous|vous en pensez quoi",
    "نظر شما چیست|نظرت چیه|شما چه فکر می کنید|به نظرتون",
    "qué opinas|que opinas|qué piensas|que piensas|qué te parece|que te parece|cuál es tu opinión",
)

# "More": the owner keeps adding ("aur ye bhi hai").
MORE = _words(
    "and also|there's also|another thing|one more thing|on top of that|plus",
    "aur ye bhi hai|aur ye bhi|ek aur masla|aur bhi hai|aur ek baat|ye bhi bura hai|ye bhi masla hai",
    "اور یہ بھی ہے|ایک اور مسئلہ|اور بھی",
    "और ये भी है|एक और समस्या|और भी है",
    "وأيضا|وأيضاً|وهناك أيضا|شيء آخر",
    "et aussi|il y a aussi|autre chose|en plus",
    "و همچنین|یک چیز دیگه|علاوه بر این",
    "y también|y tambien|además|ademas|otra cosa|hay otra cosa",
)

# Bare acknowledgements and "don't know": the fatigue signals.
ACK = _words(
    "ok|okay|k|kk|hmm|hm|hmmm|fine|sure|alright|whatever|i see|mm|mhm",
    "theek|theek hai|thik hai|acha|accha|achha|ji|jee|hmm|hn|hnn",
    "ٹھیک|ٹھیک ہے|اچھا|جی|ہمم",
    "ठीक|ठीक है|अच्छा|जी|हम्म",
    "حسنا|حسناً|تمام|طيب|اوك|حسنًا",
    "d'accord|ok|oui|bon|bien|mmh",
    "باشه|خوب|اوکی|آره|هوم",
    "vale|ok|bueno|bien|ya|mmm",
)
DONT_KNOW = _words(
    "don't know|dont know|no idea|idk|not sure|i don't know",
    "pata nahi|pata nhi|pta nahi|pta nhi|nahi pata|nhi pata|maloom nahi|malum nahi",
    "معلوم نہیں|پتا نہیں|پتہ نہیں",
    "पता नहीं|मालूम नहीं",
    "لا أعرف|لا اعرف|مش عارف|ما أدري",
    "je ne sais pas|aucune idée|aucune idee|sais pas",
    "نمی دانم|نمیدانم|نمیدونم|نمی دونم",
    "no sé|no se|ni idea|no lo sé|no lo se",
)

NUMBER = re.compile(r"\d")
WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)?", re.UNICODE)


def word_count(text: str) -> int:
    return len(WORD.findall(text or ""))


@dataclass(frozen=True)
class Signals:
    """What one message says about the dials. Nothing here is a verdict on the person."""

    openness: int = 0  # -1, 0, +1 (a jump may carry +2)
    pace: int = 0  # -1 slower, +1 faster
    mode: Mode | None = None
    trust: int = 0  # -1, 0, +1
    low: bool = False  # a one-word, "ok" or "don't know" reply
    ack: bool = False  # a bare acknowledgement ("ok", "hmm")
    hurry: bool = False
    jump: bool = False
    correction: bool = False
    trust_test: bool = False
    language: str | None = None
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Dials:
    """The state after a message. `low_streak` counts consecutive low replies (fatigue)."""

    openness: int = 1
    pace: Pace = Pace.NORMAL
    mode: Mode = Mode.LISTEN
    trust_trend: Trust = Trust.FLAT
    low_streak: int = 0
    messages_seen: int = 0
    fatigue: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "openness": self.openness,
            "pace": self.pace.name.lower(),
            "mode": self.mode.value,
            "trust_trend": self.trust_trend.name.lower(),
            "fatigue": self.fatigue,
        }


def _bare(text: str) -> str:
    return re.sub(r"[^\w\s]", " ", text or "", flags=re.UNICODE).strip().lower()


def _is_ack(text: str) -> bool:
    """The whole message is an acknowledgement of up to three words ("ok", "theek hai", "hmm")."""
    bare = _bare(text)
    if not bare or word_count(bare) > 3:
        return False
    return bool(ACK.fullmatch(bare)) or bool(ACK.search(bare) and word_count(bare) <= 2)


def read_signals(
    text: str,
    *,
    first_message: bool = False,
    gap_hours: float | None = None,
    unasked_problem: bool = False,
    repaired: bool = False,
) -> Signals:
    """Read one message. `unasked_problem`: the caller knows they raised a problem nobody asked
    about. `repaired`: pi has just repaired a correction well (trust up)."""
    text = text or ""
    n = word_count(text)
    reasons: list[str] = []
    openness = 0
    pace = 0
    trust = 0
    mode: Mode | None = None
    jump = False
    feeling = bool(FEELING.search(text))
    sensitive = bool(SENSITIVE.search(text))
    hurry = bool(HURRY.search(text))
    fix = bool(FIX.search(text))
    buy = bool(BUY.search(text))
    trust_test = bool(TRUST_TEST.search(text))
    correction = bool(CORRECTION.search(text))
    opinion = bool(OPINION.search(text))
    more = bool(MORE.search(text))
    real = bool(REAL_PROBLEM.search(text))
    ack = _is_ack(text)
    dont_know = bool(DONT_KNOW.search(text)) and n <= 4
    low = ack or dont_know or n <= 1

    if n >= LONG_MESSAGE_WORDS or NUMBER.search(text) or more:
        openness += 1
        reasons.append("long, numbers or more")
    if unasked_problem:
        openness += 1
        trust += 1
        reasons.append("unasked problem")
    if feeling:
        openness += 1
        mode = Mode.LISTEN
        reasons.append("feeling")
    if sensitive:
        openness += 1
        pace -= 1
        reasons.append("sensitive")
        if first_message or feeling or n >= LONG_MESSAGE_WORDS:
            jump = True
    if opinion:
        openness += 1
        mode = Mode.THINK
        reasons.append("opinion asked")
    if real:
        jump = True
        openness += 1
        reasons.append("real problem")
    if trust_test:
        mode = Mode.THINK
        reasons.append("trust test")
    if fix:
        mode = Mode.FIX
        pace += 1
        reasons.append("fix")
    if buy:
        mode = Mode.BUY
        pace += 1
        reasons.append("buy")
    if hurry:
        pace += 1
        if mode not in (Mode.FIX, Mode.BUY):
            mode = Mode.FIX
        reasons.append("hurry")
    if low and not (feeling or sensitive or fix or buy or hurry or opinion):
        openness -= 1
        pace += 1
        reasons.append("low reply")
    if correction:
        trust -= 1
        reasons.append("correction")
    if repaired:
        trust += 1
        reasons.append("good repair")
    if gap_hours is not None and gap_hours >= RETURN_GAP_HOURS:
        trust += 1
        reasons.append("returned after a gap")

    if jump:
        openness += 1  # a strong signal moves it a notch further
    # one signal never moves a dial by more than a notch (two on a jump)
    cap = 2 if jump else 1
    return Signals(
        openness=max(-1, min(cap, openness)),
        pace=max(-1, min(1, pace)),
        mode=mode,
        trust=max(-1, min(1, trust)),
        low=low,
        ack=ack,
        hurry=hurry,
        jump=jump,
        correction=correction,
        trust_test=trust_test,
        language=language.detect_language(text),
        reasons=tuple(reasons),
    )


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def step(prev: Dials, signals: Signals) -> Dials:
    """The dials after one message. Smoothing: a notch at a time (two on a jump); the signal wins
    over the dial; with no signal in the latest message a dial stays where it was."""
    openness = _clamp(prev.openness + signals.openness, 0, OPENNESS_MAX)
    pace = Pace(_clamp(int(prev.pace) + signals.pace, int(Pace.SLOW), int(Pace.FAST)))
    mode = signals.mode or prev.mode
    trust = int(prev.trust_trend)
    if signals.trust:
        trust = _clamp(trust + signals.trust, -1, 1)
    elif openness >= 3 > prev.openness:
        trust = _clamp(trust + 1, -1, 1)  # they confided: the conversation got warmer
    low_streak = prev.low_streak + 1 if signals.low else 0
    fatigue = signals.hurry or signals.ack or low_streak >= 2
    if fatigue:
        pace = Pace.FAST
    return Dials(
        openness=openness,
        pace=pace,
        mode=mode,
        trust_trend=Trust(trust),
        low_streak=low_streak,
        messages_seen=prev.messages_seen + 1,
        fatigue=fatigue,
    )


def update(
    prev: Dials,
    text: str,
    *,
    gap_hours: float | None = None,
    unasked_problem: bool = False,
    repaired: bool = False,
) -> Dials:
    signals = read_signals(
        text,
        first_message=prev.messages_seen == 0,
        gap_hours=gap_hours,
        unasked_problem=unasked_problem,
        repaired=repaired,
    )
    return step(prev, signals)


def estimate(messages: list[str], start: Dials | None = None) -> Dials:
    """The dials after the customer's messages, oldest first (a replay: nothing is stored)."""
    dials = start or Dials()
    for text in messages:
        dials = update(dials, text)
    return dials


def posture(dials: Dials) -> str:
    """The first approach for this dial combination (spec 2.3). For the engine only: a posture is
    never stored or shown, and it is dropped when the dials change."""
    if dials.fatigue or (dials.pace == Pace.FAST and dials.mode in (Mode.FIX, Mode.BUY)):
        return "hurried" if dials.openness >= 2 else "tester"
    if dials.openness >= 3 and dials.mode in (Mode.LISTEN, Mode.THINK):
        return "talker"
    if dials.openness <= 1 and dials.mode == Mode.THINK:
        return "skeptic"
    if dials.openness <= 1:
        return "terse"
    return "analytical" if dials.mode == Mode.THINK else "talker"


def backed_off(dials: Dials) -> Dials:
    """Repair for 'pushed for more than the client wanted' (spec 2.4): one notch back."""
    return replace(dials, openness=max(0, dials.openness - 1))
