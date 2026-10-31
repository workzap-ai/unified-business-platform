# ruff: noqa: E501  (phrase banks read better one alternative per line)
"""Platform spec v1.6, Part 19 (Engagement Engine v2.5): buying signals, direct questions, what
counts as a problem, the owner's number, no dead ends, summaries. Evidence: Live Audit 6 (Book 8),
the Artwing Studios chat of 30 October.

Pure functions. Nothing here reads the database or sends a message; the caller supplies the context
and acts on the answer. `system_ask` holds the R3 ask itself (19.2 "aap ye sab kar denge").
"""

import logging
import re
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

SUMMARY_GAP = 10  # never two summaries within this many messages (19.7)
CHECKPOINT_GAP = 8  # a checkpoint summary needs this many messages since the last one
CHECKPOINT_PROBLEMS = 3  # and at least this many problems

NUMBER_ONLY = re.compile(
    r"^\W*(?:\d[\d,.\s]*|zero|ek|do|teen|char|paanch|ten|one|two|three)\W*$", re.IGNORECASE
)


def ai_count(context: dict[str, Any]) -> int:
    """How many messages pi has sent in this chat (the clock the summary rules count in)."""
    return sum(1 for h in context.get("history") or [] if h.get("role") == "ai")


def _is_question(said: str) -> bool:
    return "?" in said or "؟" in said


def _quote_or_cost_ask(said: str) -> bool:
    from app.modules.pi import decisions

    return bool(decisions.asks_for_document(said) or decisions.cost_asked(said))


def summary_blocked(context: dict[str, Any], said: str, why: str) -> bool:
    """19.7: a summary never replaces an answer. An explicit ask for one ("list down all the
    problems", "show me", the map, "that's all") is always answered; nothing else is sent in reply
    to a number, a question or a quote request, and never twice inside ten messages."""
    if asks_for_the_quote(said):
        return True  # an explicit quote ask goes to the quote (19.2), never to a summary
    from app.modules.pi import decisions, problems

    if decisions.cost_asked(said) and why != "map":
        # a price answer is never replaced by a summary, whatever the wording ("show me the cost"),
        # unless the owner also asks for the list or the summary itself
        if not (problems.ASKS_LIST.search(said) or problems.ASKS_SUMMARY.search(said)):
            return True
    explicit = why in ("show", "map", "document_asked")
    sent_at = (context.get("brief") or {}).get("summary_at")
    if not explicit and isinstance(sent_at, int) and ai_count(context) - sent_at < SUMMARY_GAP:
        return True
    if why == "checkpoint":
        return _is_question(said) or bool(NUMBER_ONLY.match(said)) or _quote_or_cost_ask(said)
    if why == "done":
        return _quote_or_cost_ask(said)
    return False


def checkpoint_due(context: dict[str, Any], said: str, noted: int) -> str | None:
    """19.7: at least three problems, the last summary at least eight messages ago (or never), and
    the owner not mid-question. Returns "checkpoint" or None."""
    if noted < CHECKPOINT_PROBLEMS or _is_question(said):
        return None
    sent_at = (context.get("brief") or {}).get("summary_at")
    if isinstance(sent_at, int) and ai_count(context) - sent_at < CHECKPOINT_GAP:
        return None
    return "checkpoint"


# 19.6 noDeadEnd: promises to stop asking, "those are all the ideas", "none of it is solved yet", and
# a blanket "it is all noted here" (a claim that must match the stored list, and 17.6 says pi does not
# announce noting at all).
DEAD_ENDS = (
    (
        re.compile(
            r"\b(?:koi |aur )?(?:naya|nayi|aur) sawal(?:at)? (?:nahi|nahin|nhi) (?:poochh|puch|pooch)\w*"
            r"|\bab main (?:koi )?(?:aur )?sawal(?:at)? nahi\b"
            r"|\bno (?:more|further) questions\b"
            r"|\bi (?:will not|won'?t|shall not|will no longer) (?:ask|be asking)\b"
            r"|\b(?:wont|won't) ask (?:you )?(?:any )?(?:more|again)\b",
            re.IGNORECASE,
        ),
        "do not promise to stop asking: say the next step instead (for example that you move on to the quote)",
    ),
    (
        re.compile(
            r"\bitne hi ideas\b|\bthose are (?:all )?the ideas\b|\bthis is all the ideas\b|\bthat is all i can give\b"
            r"|\bnothing more to give\b|\byahan (?:itna|itne) hi\b|\bkoi aur idea nahi\b|\bno more ideas\b",
            re.IGNORECASE,
        ),
        "do not say the ideas are used up: ask what they tried and what happened, then give different ideas or move to the quote",
    ),
    (
        re.compile(r"کوئی نیا سوال نہیں|لن أطرح أي سؤال|لا مزيد من الأسئلة"),
        "do not promise to stop asking: say the next step instead",
    ),
    (
        re.compile(
            r"\bnone of it is solved\b|\bnothing (?:here )?is solved yet\b|\binme se abhi kuch bhi hal nahi\b",
            re.IGNORECASE,
        ),
        "do not tell the owner nothing is solved: say what happens next",
    ),
    (
        re.compile(
            r"\b(?:wo|woh|ye|yeh) sab (?:yahan |yaha )?note (?:hai|hain|ho gaya)\b"
            r"|\b(?:it(?:'s| is)|everything is|all of it is) (?:all )?noted\b"
            r"|\bi(?:'ve| have) noted (?:all|everything)\b",
            re.IGNORECASE,
        ),
        "do not say everything is noted: say only what is stored, in the owner's words",
    ),
)


def dead_end(reply: str) -> str | None:
    """The first dead end or false claim in a drafted reply (19.6), or None."""
    said = " ".join((reply or "").split())
    for pattern, reason in DEAD_ENDS:
        if pattern.search(said):
            return reason
    return None


# 19.4 problemFilter: what is a problem and what is not. A question (about price, about pi), a
# complaint about pi and a goal on its own are never stored as problems; a want goes to the wants list.
WANT_CUE = re.compile(
    r"\b(?:chahiye|chahta|chahte|chahti|banana hai|banwana|banwani|karvani|karwani|karwana|karvana|"
    r"lagana hai|chalani hai|chalana hai|i want|we want|i need|we need|need a|want a|build|set up)\b",
    re.IGNORECASE,
)
GOAL_ONLY = re.compile(
    r"\b(?:sales|business|revenue)\b.{0,20}\b(?:badh\w*|barh\w*|grow\w*|increase\w*)\b"
    r"|\b(?:grow|increase|badha\w*)\b.{0,15}\b(?:sales|business)\b",
    re.IGNORECASE,
)
PRICE_QUESTION = re.compile(
    r"\?|\b(?:hoga|lagega|will it cost|would it cost|will that cost)\b", re.IGNORECASE
)
MAX_WANTS = 12


def want_cue(said: str) -> bool:
    """A long enough message that says what the owner wants built or done (19.4)."""
    return len((said or "").split()) >= 10 and bool(WANT_CUE.search(said or ""))


def not_a_problem(user_words: list[str]) -> str | None:
    """Why a note made from these words is not a problem (19.4), or None."""
    from app.modules.pi import box_signals, decisions, problems

    blob = " ".join(user_words or [])
    if not blob.strip():
        return None
    if len(blob.split()) <= 12 and decisions.cost_asked(blob) and PRICE_QUESTION.search(blob):
        return "is a question about price: answer it, never note it as a problem"
    if box_signals.REPEAT_COMPLAINT.search(blob):
        return "is frustration with pi, not a business problem: repair, never note it"
    if GOAL_ONLY.search(blob) and not problems.PROBLEM_CUE.search(blob):
        return "is a goal, not a problem: attach it to the problem it comes from, never alone"
    return None


def merge_wants(brief: dict[str, Any], found: list[str] | None) -> dict[str, Any]:
    """The brief with new wants added (their own words, no repeats, oldest kept)."""
    if not found:
        return brief
    have = [str(w) for w in brief.get("wants") or []]
    seen = {w.casefold() for w in have}
    from app.modules.pi import safety
    from app.modules.pi.problems import redact

    for want in found:
        # a third party introduced by a role keeps only the role (R-PRIV-01), then card, ID, phone and
        # email go; both before the cut, so a number split at the boundary cannot escape
        said = safety.redact_pii(" ".join(str(want).split())).text
        want = redact(said)[0][:120]
        if want and want.casefold() not in seen and len(have) < MAX_WANTS:
            have.append(want)
            seen.add(want.casefold())
    return {**brief, "wants": have}


# 19.2 buyingSignal: R1 (the owner asks for the quote or the price of the thing discussed) and R3
# (ready to buy, with a clear brief). A signal starts the quote through the same decision gate as
# "send me the quote"; pi never gives a price.
NEGATED = re.compile(
    r"\b(?:nahi|nahin|nhi|not|no|don'?t|without|later|baad mein|baad me|kam|tight|limited|low|short|"
    r"bohat kam|bahut kam)\b",
    re.IGNORECASE,
)
# the owner's own loss or waste ("how much is lost", "kitna maal kharab hua") is a statement, not a price ask
OWN_LOSS = re.compile(
    r"\b(?:zaya|nuksan|loss|lost|losing|kharab|waste|wasted|ja raha|jata hai|gaya|going out)\b",
    re.IGNORECASE,
)
R1_QUOTE = re.compile(
    r"\b(?:quote|quotation)\W{0,3}(?:abhi\s+|jaldi\s+)?(?:do|dein|den|dijiye|bhejo|bhej do|chahiye)\b"
    r"|\b(?:mujhay|mujhe|hamein|humein|hamen)\s+(?:ab\s+|abhi\s+)?(?:quote|quotation)\b"
    r"|\bgive me (?:the |a )?(?:quote|quotation|price)\b|\bsend (?:me )?(?:the |a )?(?:quote|quotation)\b",
    re.IGNORECASE,
)
R1_PRICE = re.compile(
    r"\bkitna\s+(?:kharcha|kharch|lagega|lagay\s?ga|paisa|cost)\b(?!\s+(?:\d+\s+)?(?:time|waqt|din|dinon|dino|hafte|haftay|hafton|haftoon|mahine|mahinay|mahinon|"
    r"mahino|mahina|ghante|ghanta|ghantay|ghanton|saal|sal|saalon|minute|minutes|mint|"
    r"weeks?|months?|days?|hours?|years?)\b)"
    r"|\bkharcha\s+(?:kitna|hoga)\b"
    r"|\bkitne\s+(?:paise|rupay|rupees)\b|\bhow much (?:will|would|does|for)\b"
    r"|\bwhat(?:'s| is| will be) the (?:price|cost)\b|\b(?:price|rate|cost)\s+kya\b",
    re.IGNORECASE,
)
R3_READY = re.compile(
    r"\bbudget\b.{0,25}\b(?:ready|hai|tayyar|available)\b"
    r"|\b(?:paisa|paise|budget)\s+lagane\b.{0,25}\b(?:ready|tayyar)\b"
    r"|\b(?:ready|tayyar)\b.{0,25}\b(?:budget|paisa|paise|invest)\b"
    r"|\bkab\s+shuru\s+kar\s+sakte\b|\bready to (?:invest|pay|start)\b|\bpaise\s+lagayenge\b",
    re.IGNORECASE,
)
THIN_BRIEF = 2  # problems plus wants: fewer than this and the reply adds the one line to widen


def buying_signal(said: str, covers: int = 0) -> str | None:
    """ "R1" when the owner asks for the quote or the price, "R3" when they say they are ready to buy
    and the brief holds at least two things (19.2), else None. A "not" in the sentence cancels it."""
    from app.modules.pi import decisions

    text = " ".join(decisions.OWN_MONEY.sub(" ", said or "").split())
    if not text:
        return None
    if R1_QUOTE.search(text) or R1_PRICE.search(text):
        if NEGATED.search(text) or (R1_PRICE.search(text) and OWN_LOSS.search(text)):
            return None
        return "R1"
    if R3_READY.search(text) and covers >= 2 and not NEGATED.search(text):
        return "R3"
    return None


# D-1 gate. FAIL CLOSED: a false negative (the owner asks again; R3 still opens the offer) is
# acceptable, a quote starting on a statement is not (R-SELL, no quote while listening).
# 1. vetoes (negation, "later", price, "only when", can't/don't, before/after/explain) apply to the
#    WHOLE message, never per clause; a benign tail ("na", "no rush") is removed first;
# 2. reported speech ("my customers say, send me the quote") blocks, except the narrow lead-in
#    "I said / maine bataya / I already told you" directly before the ask;
# 3. the ask is an IMPERATIVE addressed to pi, then the document noun, and it ENDS the clause. The
#    bare "I/we want/need <noun>" is not an ask here ("we need a quote system that tracks orders").
_CLAUSE_END = re.compile(r"[.,;!?؟؛\n]+|\s(?:but|and|aur|lekin|phir|so)\s", re.IGNORECASE)
_CLAUSE_CONJ = re.compile(r"^\W*(?:so|but|and|aur|lekin|phir|toh)\s+", re.IGNORECASE)
_BENIGN_TAIL = re.compile(
    r"\b(?:no rush|no hurry|no worries)\b|\bna\b(?=\s*(?:[,.!?;]|$))", re.IGNORECASE
)
_ONLY_WHEN = re.compile(r"\bonly\s+when\b|\bsirf\s+jab\b|\bwhen\s+i\s+say\b", re.IGNORECASE)
_SAID_LEAD = re.compile(
    r"^\W*(?:i|we|maine|main ne|humne|hum ne)\s+(?:(?:already|just|have|had|did|sab)\s+)*"
    r"(?:said|told you|asked|kaha|bola|bataya|bata diya)\W+(?:(?:that|ke)\s+)?",
    re.IGNORECASE,
)
_REPORTED = re.compile(
    r"\b(?:say|says|said|told|tell|tells|asked|asks|kaha|kehte|kehta|kehti|bola|bolte|boli|bolta)\b",
    re.IGNORECASE,
)
_NOUN = (
    r"(?:(?:solution|full|final|rough|short|quick|proper)\s+)?(?:document|quote|quotation|proposal)"
)
_TAIL = r"(?:\s+(?:please|pls|plz|now|today|asap|na|abhi|jaldi|ab|do|dein|den))*"
_ASK_EN = re.compile(
    r"^(?:(?:yes|ok|okay|haan|ji)\W+)*(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
    r"(?:(?:i|we)\s+(?:want|need|would like)\s+you\s+to\s+)?(?:please\s+)?"
    r"(?:send|give|prepare|make|create|share)(?:\s+(?:me|us))?(?:\s+(?:the|a|my|our))?\s+"
    rf"{_NOUN}{_TAIL}\W*$",
    re.IGNORECASE,
)
_ME = r"(?:(?:mujhe|mujhay|hamein|hamen|humein)\s+)?"
_UR_VERB = r"(?:de|dein|den|dain|do|dedo|de do|dijiye|dijiyega|bhej\w*|bhij\w*|bana\w*|banwa\w*)"
_ASK_UR = re.compile(
    r"^(?:(?:yes|ok|okay|haan|ji|please)\W+)*(?:(?:ab|abhi|jaldi|please)\s+)*"
    rf"{_ME}(?:(?:ab|abhi|jaldi|please)\s+)*{_NOUN}\s+{_ME}{_UR_VERB}{_TAIL}\W*$"
    rf"|^(?:(?:yes|ok|okay|haan|ji|please)\W+)*(?:(?:ab|abhi|jaldi|please)\s+)*{_UR_VERB}\s+"
    rf"{_ME}{_NOUN}{_TAIL}\W*$",
    re.IGNORECASE,
)


def asks_for_the_quote(said: str) -> bool:
    """The owner explicitly asks pi for the quote itself (see the rules above): "send me the quote",
    "mujhay quote do abhi", "can you send me the quote?", "I said give me the quote". A price
    QUESTION ("how much would it cost?", "give me the price") is answered first (RSOL08) and never
    starts the quote at the decision gate (owner decision D-1)."""
    from app.modules.pi import decisions

    whole = " ".join((said or "").split())
    if not whole:
        return False
    plain = _BENIGN_TAIL.sub(" ", whole)
    if decisions.NOT_A_REQUEST.search(plain) or _ONLY_WHEN.search(plain):
        return False  # a refusal, "later", a price word or a condition anywhere vetoes the ask
    body = _SAID_LEAD.sub("", whole, count=1)
    if _REPORTED.search(body):
        return False  # reported speech is not an ask addressed to pi
    for clause in _CLAUSE_END.split(body):
        clause = _CLAUSE_CONJ.sub("", clause.strip()).strip()
        if clause and (_ASK_EN.match(clause) or _ASK_UR.match(clause)):
            return True
    return False


def gate_signal(said: str, covers: int = 0) -> str | None:
    """The signal the decision gate may act on: "R1" only for an explicit ask for the quote (D-1).
    A price question stays an R1 signal for the offer (`buying_signal`) but starts nothing here, and
    R3 (ready to buy) only opens the offer."""
    return "R1" if asks_for_the_quote(said) else None


def ready_to_buy(said: str) -> bool:
    """The owner says they are ready to buy (R3 wording, 19.2); a plain yes only: "not", "tight" or
    "low" cancels it."""
    from app.modules.pi import decisions

    text = " ".join(decisions.OWN_MONEY.sub(" ", said or "").split())
    return bool(R3_READY.search(text)) and not NEGATED.search(text)


COVERS_LINES = {
    "en": (
        "I will note these for the document that the team reviews: {items}.",
        "If you want anything else added, tell me.",
    ),
    "roman_ur": (
        "Main ye us document ke liye note kar raha hoon jo team dekhti hai: {items}.",
        "Koi aur cheez shamil karni ho to bata dein.",
    ),
    "ar": ("سأدوّن هذه للوثيقة التي يراجعها الفريق: {items}.", "إن أردت إضافة شيء آخر فأخبرني."),
}


def covers_lines(language: str, items: list[str]) -> str:
    """The lines after a buying signal (19.2): what the quote covers in the owner's words, and, when
    the set is thin, the one line to widen. No price, no question."""
    items = [i for i in items if i]
    if not items:
        return ""
    cover, widen = COVERS_LINES.get(language, COVERS_LINES["en"])
    lines = [cover.format(items="; ".join(items[:8]))]
    if len(items) < THIN_BRIEF:
        lines.append(widen)
    return "\n".join(lines)


# 19.5 numberUsed: when the owner's short answer is a number or a quantity ("Zero", "10 crore", "teen
# mahine"), the next reply must use it, not repeat a summary.
NUMBER_TOKEN = re.compile(
    r"\b(?:\d[\d,.]*(?:\s?(?:crore|lakh|lac|k|%|percent))?|zero|(?:ek|do|teen|char|chaar|paanch|panch|chhe|saat|aath|nau|das|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:mahine?|din|hafte|haftay|saal|baar|log|customers?|months?|days?|weeks?|years?|times))\b",
    re.IGNORECASE,
)
ZERO_FORMS = ("zero", "0", "ek bhi nahi", "koi nahi", "none", "no one", "nothing")
SHORT_ANSWER_WORDS = 8


def number_used(reply: str, said: str) -> str | None:
    """A reason when the owner's short message holds a number and the reply never uses it."""
    said = " ".join((said or "").split())
    if not said or len(said.split()) > SHORT_ANSWER_WORDS or "?" in said:
        return None
    found = [m.group(0).strip() for m in NUMBER_TOKEN.finditer(said)]
    if not found:
        return None
    mine = (reply or "").casefold()
    for token in found:
        low = token.casefold()
        if low in mine or (low == "zero" and any(z in mine for z in ZERO_FORMS)):
            return None
    return (
        f'the owner just gave a number ("{found[0]}"): use it in the reply (say what it means for the '
        "problem, link it to what they told you, or ask what is behind it). Do not repeat a summary"
    )


# 19.3 directQuestion: "listen again" / "say that again" after a voice note gets a playback of what pi
# understood, built from what is stored (the problems and the wants), never a request to repeat.
REPLAY_ASK = re.compile(
    r"\b(?:wapis|waapis|dobara|phir se|dubara)\s+(?:suna\w*|sun\w*|bol\w*|bata\w*|kah\w*)\b"
    r"|\b(?:listen|say|tell me|play)(?: that| this| it)?(?: back| again)\b"
    r"|\b(?:repeat|replay) (?:that|this|it|what)\b|\bwhat did you (?:hear|understand)\b"
    r"|\bkya (?:suna|samjha|samjhe)\b",
    re.IGNORECASE,
)
PLAYBACK = {
    "en": "Here is what I understood: {items}. Tell me if anything is wrong or missing.",
    "roman_ur": "Ji, jo maine suna: {items}. Kuch ghalat ya reh gaya ho to bataiye.",
    "ar": "هذا ما فهمته: {items}. أخبرني إن كان هناك شيء خاطئ أو ناقص.",
}


def asks_replay(said: str) -> bool:
    return bool(REPLAY_ASK.search(" ".join((said or "").split())))


def playback(language: str, items: list[str]) -> str:
    """Two or three lines of what pi understood, from the stored problems and wants (19.3)."""
    items = [i for i in items if i]
    if not items:
        return ""
    return PLAYBACK.get(language, PLAYBACK["en"]).format(items="; ".join(items[:8]))


def replay(turn: Any, context: dict[str, Any]) -> None:
    """ "Yeh wapis sunay please": the reply becomes a playback of what pi understood (19.3)."""
    if getattr(turn, "_summary", False) or getattr(turn, "_decision", None) is not None:
        return
    if ai_count(context) == 0:
        return  # a first message carries the AI disclosure and the opening, never a playback
    if not asks_replay(str(context.get("latest_customer_message") or "")):
        return
    language = str(context.get("reply_language") or "en")
    own = "title_local" if language != "en" else "title"
    items = [
        str(p.get(own) or p.get("title") or "") for p in context.get("noted_problems") or []
    ] + [str(w) for w in (context.get("brief") or {}).get("wants") or []]
    line = playback(language, items)
    if line:
        turn.reply = line
        turn.awaiting_customer = True


MAX_CHARS = 20_000  # the check reads a reply up to this long; above it the plain cap is applied


def statement_only(reply: str) -> str:
    """The reply with every question turned into a statement (R-ASK-01): used before the offer is
    appended, so the offer is the only question of the message and it is last. A question is demoted,
    never dropped: its mark becomes a full stop and the whole sentence stays, so a sentence that must
    be said (the AI disclosure, a refusal to ask for card or password details, a safety referral) can
    never be lost, whatever its language or wording."""
    text = (reply or "").strip()
    if not text:
        return ""
    if len(text) > MAX_CHARS:
        return _oversize(text, keep_one=False)
    try:
        guarded, held = protect_urls(text)
        flat = protect_abbreviations(normalise_question_marks(guarded))
        return _demote(flat, held, [], keep_one=False).strip()
    except Exception as error:  # noqa: BLE001 - the reply must still be sent, and still without questions
        logger.warning("pi_statement_only_failed", extra={"error_type": type(error).__name__})
        return _fallback(text, keep_one=False).strip()


# --- R-ASK-01 on the FINAL text ---------------------------------------------------------------------
# What counts as a question mark and as the end of a question. A question may be followed by a closing
# quote, a bracket, a WhatsApp bold or italic mark, an emoji, a zero-width character or an RTL mark, and
# may be glued to the next sentence; "?!", "?." and "?..." are one question mark.
# Never counted and never rewritten: a "?" in a link, in a code span (`...` or a fenced block), in a
# "x ? y : z" expression, or in words quoted in the middle of a sentence that hold exactly one question
# mark. A quotation that is a whole sentence with exactly one mark IS a question (counted, and demoted by
# changing only its mark); a quotation holding several marks is ordinary text and is counted as such.
# A dot in an abbreviation or a decimal ends nothing; an inch mark (5") opens no quotation.
#
# Known limits (documented, not hidden): a quotation embedded in a sentence with one mark is not
# counted; a question written with no question mark at all (any script) cannot be told from a
# statement; the Armenian mark sits inside the word and an ASCII ";" is a semicolon; the check runs
# only in brain mode; a ternary is recognised only in its plain "a ? b : c" shape.
EMOJI = (
    r"\U0001F000-\U0001FFFF\u2190-\u21ff\u2300-\u23ff\u2460-\u24ff\u25a0-\u27bf\u2900-\u297f"
    r"\u2b00-\u2bff\u3030\u303d\u3297\u3299\u20e3\ufe0f\U000e0020-\U000e007f"
)
ZERO_WIDTH = r"\u200b-\u200f\u2060\ufeff\u2066-\u2069\u061c\u202a-\u202e"
CLOSER_CHARS = "*_~\"'”’)\\]»›"
MARKS = "?؟？⁇⁈⁉\u037e⸮፧"  # every question mark the check knows
CODE = re.compile(r"```.*?```|`[^`\n]+`", re.DOTALL)
URL = re.compile(r"https?://\S*[^\s?.!,;:)\]»]")
TERNARY = re.compile(r"\S+ \? [^?؟\n:]{1,80} : \S+")
# A straight quotation opens after a space or a mark (never after a letter or digit: 5" is an inch mark)
# and closes before one (never before a letter or digit); curly quotes and guillemets are unambiguous.
QUOTED = re.compile(
    r'(?<![\w"])"(?=\S)[^"\n]{1,300}?(?<=\S)"(?![\w"])|“[^”\n]{1,300}”|«[^»\n]{1,300}»'
)
# the marks that end a sentence or a line: a quotation after them, or before them, is a sentence of its own
SENTENCE_ENDS = ".!?؟۔।…\n\r"
QUESTION_MARK_VARIANTS = str.maketrans(
    {"？": "?", "⁇": "?", "⁈": "?", "⁉": "?", "\u037e": "?", "⸮": "?", "፧": "?"}
)
ANY_MARK = re.compile(f"[{MARKS}]")
CLOSERS = re.compile(rf"([?؟.!۔।])([{CLOSER_CHARS}]+)(?=[.!…]*(?:\s|$))")
SPLIT_AFTER = re.compile(rf"([?؟.!۔।][{CLOSER_CHARS}]*)(?=[{EMOJI}{ZERO_WIDTH}])")
MARK_RUN = re.compile(r"([?؟])[?؟!.…]+")
GLUED = re.compile(rf"([?؟][{CLOSER_CHARS}]*)(?=[^\W\d_])")
TRAILING = re.compile(rf"[\s{ZERO_WIDTH}{EMOJI}{CLOSER_CHARS}]+$")
ABBREVIATION = re.compile(r"(?i:\b(?:e\.g|i\.e|vs|rs|mr|mrs|dr)\.)(?=\s)")
LIST_NUMBER = re.compile(r"(?m)^([ \t]*\d{1,2})\.(?=\s)")
DOT_LEADER = "\u2024"
PLACEHOLDER = "URLPLACEHOLDER"
HELD_TOKEN = re.compile(rf"{PLACEHOLDER}(\d+)([QX])([?.]?)")


def _embedded(text: str, start: int, end: int) -> bool:
    """The quotation at text[start:end] sits in the middle of a sentence: words come before it on its
    line and more words follow it. A quotation that is a whole sentence, or that begins or ends one
    (or the reply), is not embedded."""
    before = text[:start].rstrip(" \t")
    after = text[end:].lstrip(" \t")
    if not before or before[-1] in SENTENCE_ENDS or not after:
        return False
    return after[0] not in SENTENCE_ENDS and (after[0].isalnum() or after[0] in ",;:)-—")


def protect_urls(text: str) -> tuple[str, list[str]]:
    """The text with each code span, link, ternary and quotation holding one question mark replaced by
    a placeholder, and what was held, so a "?" there is never counted by accident or rewritten. A
    quotation that is a whole sentence with one mark is held too, but its mark stays counted outside it
    (a placeholder ending in "Q?"), so the cap sees it; a quotation with several marks is not held: it
    is ordinary text, counted and capped like any other."""
    held: list[str] = []

    def hold(match: "re.Match[str]") -> str:
        held.append(match.group(0))
        return f"{PLACEHOLDER}{len(held) - 1}X"

    def hold_quotation(match: "re.Match[str]") -> str:
        quoted = match.group(0)
        marks = len(ANY_MARK.findall(quoted))
        if marks >= 2:
            return quoted
        held.append(quoted)
        token = f"{PLACEHOLDER}{len(held) - 1}"
        if marks == 0 or _embedded(match.string, match.start(), match.end()):
            return f"{token}X"
        # a quotation that is a sentence of its own stands apart from what is glued to it, so it can
        # never be merged into a neighbouring sentence and rewritten by accident
        before, after = match.string[: match.start()], match.string[match.end() :]
        lead = " " if before and not before[-1].isspace() else ""
        trail = " " if after and not after[0].isspace() else ""
        return f"{lead}{token}Q?{trail}"

    held_text = TERNARY.sub(hold, URL.sub(hold, CODE.sub(hold, text)))
    return QUOTED.sub(hold_quotation, held_text), held


def _quotation_back(value: str) -> "Callable[[re.Match[str]], str]":
    """A replacement that puts a held quotation back exactly as it was (a regex replacement string
    would read a backslash in the words as an escape). When the sentence's mark was turned into a full
    stop (the placeholder ends in "."), only the quotation's own question marks become full stops."""
    demoted = ANY_MARK.sub(".", value)

    def put(match: "re.Match[str]") -> str:
        return demoted if match.group(1) == "." else value

    return put


def restore_urls(text: str, held: list[str]) -> str:
    """The held text put back. A whole-sentence quotation whose mark was turned into a full stop comes
    back with its own mark turned into a full stop too (the words are untouched)."""
    for n in reversed(range(len(held))):
        text = re.sub(rf"{PLACEHOLDER}{n}Q([?.]?)", _quotation_back(held[n]), text)
        text = text.replace(f"{PLACEHOLDER}{n}X", held[n])
    return text


def normalise_question_marks(text: str) -> str:
    """Full-width, double and other scripts' question marks become "?"; a mark directly followed by an
    emoji, a zero-width character or an RTL mark gets a space after it; a closing quote, bracket or
    bold mark moves behind the mark ("*Which one?*" -> "*Which one*?"); "?!", "?." and "?..." become
    "?"; and two questions glued together ("Is it A?Is it B?") are separated."""
    text = MARK_RUN.sub(r"\1", text.translate(QUESTION_MARK_VARIANTS))
    text = GLUED.sub(r"\1 ", SPLIT_AFTER.sub(r"\1 ", text))
    return MARK_RUN.sub(r"\1", CLOSERS.sub(lambda m: m.group(2) + m.group(1), text))


def protect_abbreviations(text: str) -> str:
    """The dot of an abbreviation ("e.g.", "Rs.", "Dr.") or of a list number at the start of a line
    ("1. Which one?") becomes a dot leader, so no sentence ends there. A year or a figure inside a
    line ("We started in 2024.") still ends its sentence."""
    text = ABBREVIATION.sub(lambda m: m.group(0)[:-1] + DOT_LEADER, text)
    return LIST_NUMBER.sub(lambda m: m.group(1) + DOT_LEADER, text)


def restore_abbreviations(text: str) -> str:
    return text.replace(DOT_LEADER, ".")


def ends_in_question(text: str) -> bool:
    """The text ends in a question mark, ignoring trailing closers, zero-width marks and emoji."""
    return TRAILING.sub("", text or "").endswith(("?", "؟"))


def question_count(text: str) -> int:
    """Question marks in text that has had its links protected and its marks normalised."""
    return text.count("?") + text.count("؟")


def _ends_question(sentence: str) -> bool:
    return sentence.rstrip().endswith(("?", "؟"))


def _as_statement(sentence: str) -> str:
    """The sentence with its closing question mark turned into a full stop (same length)."""
    body = sentence.rstrip()
    return body[:-1] + "." + sentence[len(body) :] if _ends_question(sentence) else sentence


def _original(sentence: str, held: list[str]) -> str:
    return restore_abbreviations(restore_urls(sentence, held))


def sentence_spans(flat: str) -> list[tuple[int, int, str]]:
    """The sentences of a normalised text with their positions, in order (a repeated sentence has
    its own position, so a change is made where it stands and never at an earlier copy)."""
    from app.modules.pi import constitution

    spans: list[tuple[int, int, str]] = []
    pos = 0
    for sentence in constitution._sentences(flat):
        start = flat.find(sentence, pos)
        if start < 0:
            continue
        spans.append((start, start + len(sentence), sentence))
        pos = start + len(sentence)
    return spans


# What must never be deleted or weakened, in every supported language (en, roman_ur, ur, ar, hi): the
# AI disclosure, a refusal to ask for card, password, code or identity details, a safety referral.
# A question is only ever demoted, never dropped, so nothing here can delete a sentence: these rules
# choose which question survives when there are several (an ordinary one before a mandatory one).
AI_ANY = re.compile(
    r"\bAI\b|\bA\.I\.|artificial intelligence|مصنوعی ذہانت|مصنوعی ذھانت|اے آئی|ذكاء اصطناعي|"
    r"एआई|ए\.?\s?आई|कृत्रिम बुद्धिमत्ता|आर्टिफिशियल इंटेलिजेंस|आर्टिफ़िशियल इंटेलिजेंस",
    re.IGNORECASE,
)
SELF_REF = re.compile(
    r"\bI(?:'m|’m| am)\b|\bmain\b.{0,40}\b(?:hoon|hun|hu)\b|میں.{0,40}ہوں|मैं.{0,40}(?:हूँ|हूं)|أنا",
    re.IGNORECASE,
)
NAMES_PI = re.compile(r"\bpi\b|\bWorkzap\b", re.IGNORECASE)
AI_WORD = r"(?:\bAI\b|artificial intelligence|اے آئی|مصنوعی ذہانت|ذكاء اصطناعي|एआई|ए\.?\s?आई|आर्टिफिशियल|कृत्रिम बुद्धिमत्ता)"
# pi or Workzap named right beside the AI word ("I am pi, an AI from Workzap", "Workzap ka AI"): that is
# the disclosure itself, whatever else the same sentence says (a "your bot" later on does not undo it)
PI_IS_AI = re.compile(
    rf"(?:\bpi\b|\bWorkzap\b).{{0,25}}{AI_WORD}|{AI_WORD}.{{0,25}}(?:\bpi\b|\bWorkzap\b)",
    re.IGNORECASE,
)
DIRECT_SELF_AI = re.compile(
    rf"\bI(?:'m|’m| am)\s+(?:(?:an?|the)\s+(?:\w+\s+)?)?{AI_WORD}|"
    rf"\bmain\s+(?:ek\s+)?{AI_WORD}(?:\s+\S+){{0,2}}\s*(?:hoon|hun|hu)\b|"
    rf"میں\s+(?:ایک\s+)?{AI_WORD}(?:\s+\S+){{0,2}}\s+ہوں|"
    rf"मैं\s+(?:एक\s+)?{AI_WORD}(?:\s+\S+){{0,2}}\s+(?:हूँ|हूं)|أنا\s+(?:(?:مساعد|برنامج|نظام|روبوت)\s+)?{AI_WORD}",
    re.IGNORECASE,
)
BUSINESS_BOT = re.compile(
    r"\b(?:your|aap ka|aap ki|aapka|aapki)\b.{0,30}\b(?:bot|robot|chatbot|AI)\b|"
    r"(?:آپ کا|آپ کی).{0,30}(?:بوٹ|اے آئی)|(?:आपका|आपकी).{0,30}(?:बॉट|एआई)",
    re.IGNORECASE,
)
PAY_ID_WORDS = re.compile(
    r"\bcards?\b|\bpassword\b|\bOTP\b|\bCVV\b|\bPIN\b|\bID\b|\bCNIC\b|\bpassport\b|\bcredit\b|\bdebit\b|"
    r"\bbank\b|\baccount number\b|\bIBAN\b|\bpayments?\b|\bpay\b|کارڈ|پاس ورڈ|پاسورڈ|او ٹی پی|شناختی|"
    r"بینک|ادائیگی|कार्ड|पासवर्ड|ओटीपी|आईडी|बैंक|क्रेडिट|डेबिट|भुगतान|بطاقة|كلمة المرور|رمز|بنك|"
    r"هوية|دفع",
    re.IGNORECASE,
)
REFUSE_WORDS = re.compile(
    r"\bnever\b|\bdon'?t\b|\bdo not\b|\bnot\b|\bno need\b|\bwithout\b|\bcan'?t\b|\bcannot\b|"
    r"\bwon'?t\b|\bunable\b|\bnahi\b|\bnahin\b|\bkabhi\b|\bhargiz\b|\bmat\b|کبھی نہیں|نہیں|ہرگز|"
    r"ضرورت نہیں|کر سکتا|کر سکتی|कभी नहीं|नहीं|हरगिज़|لا |أبدًا|أبدا",
    re.IGNORECASE,
)
ASK_VERBS = re.compile(
    r"\bask(?:s|ing)?\b|\brequest\b|\bneed\b|\bshare\b|\bsend\b|\bgive\b|\benter\b|\bprovide\b|\btell\b|"
    r"\btype\b|\bwrite\b|\bput\b|\btake\b|\baccept\b|\bcollect\b|\btext\b|\bpaste\b|"
    r"maang|mang|poochh|puch|bhej|bata|likh|le sak|مانگ|پوچھ|بھیج|دیں|بتا|مت|لکھ|لے سک|"
    r"मांग|पूछ|भेज|बता|दें|लिख|ले सक|أطلب|اطلب|أرسل|ترسل|تشارك|تعطي|أعطي|أقبل|أكتب|اكتب",
    re.IGNORECASE,
)
SAFETY_WORDS = re.compile(
    r"\bambulance\b|\bpolice\b|\bhospital\b|\bemergency\b|\bdoctor\b|\bfire brigade\b|\bpolis\b|"
    r"\baspatal\b|ایمبولینس|پولیس|ہسپتال|اسپتال|ایمرجنسی|ڈاکٹر|فائر بریگیڈ|एम्बुलेंस|एंबुलेंस|पुलिस|"
    r"अस्पताल|आपातकालीन|डॉक्टर|إسعاف|الإسعاف|الشرطة|الطوارئ|مستشفى|طبيب|الدفاع المدني",
    re.IGNORECASE,
)
CALL_WORDS = re.compile(
    r"\bcall\b|\bdial\b|\bring\b|\bgo to\b|\bcontact\b|\bvisit\b|\bbula\w*|\bjayen\b|\bjaen\b|\bjaiye\b|"
    r"\bjao\b|کال|فون|بلائیں|بلاؤ|جائیں|جائیے|جاؤ|جانا|کریں|कॉल|फोन|बुलाएं|बुलाइए|जाएं|जाइए|जाइये|"
    r"जाओ|जाना|اتصل|اطلب|اذهب|زر",
    re.IGNORECASE,
)
MIN_KEEP = (
    8  # a kept line shorter than this (once normalised) matches nothing: it would match anything
)


def discloses_ai(sentence: str) -> bool:
    """The sentence says, about pi itself, that it is an AI ("I am pi, an AI from Workzap", "Main pi
    hoon, Workzap ka AI", "I'm an AI assistant"). A question about someone's chatbot business is not
    one."""
    if not AI_ANY.search(sentence) or not SELF_REF.search(sentence):
        return False
    if DIRECT_SELF_AI.search(sentence) or PI_IS_AI.search(sentence):
        return True
    return bool(NAMES_PI.search(sentence)) and not BUSINESS_BOT.search(sentence)


def refuses_secrets(sentence: str) -> bool:
    """A refusal to ask for card, password, code or identity details, or to take payment in chat: a
    payment or identity word, a refusal word and a verb of asking or taking, together."""
    from app.modules.pi import constitution

    return bool(
        PAY_ID_WORDS.search(sentence)
        and (REFUSE_WORDS.search(sentence) or constitution.REFUSING.search(sentence))
        and ASK_VERBS.search(sentence)
    )


def refers_to_safety(sentence: str) -> bool:
    """A safety referral is shaped like one: a verb of calling or going, with the emergency number or
    a service word. A number next to "doctor" or "hospital" is not one."""
    from app.modules.pi import solution_rules

    service = SAFETY_WORDS.search(sentence) or solution_rules.EMERGENCY_NUMBER.search(sentence)
    return bool(CALL_WORDS.search(sentence) and service) or bool(
        solution_rules.REFER_TO.search(sentence)
    )


def _canon(text: str) -> str:
    """A sentence reduced for comparing fixed lines: marks and closers at the end, zero-width
    characters, case and spacing do not matter."""
    text = re.sub(rf"[{ZERO_WIDTH}]", "", text.translate(QUESTION_MARK_VARIANTS))
    text = restore_abbreviations(text)
    tail = rf"[\s{EMOJI}{CLOSER_CHARS}?؟.!۔।…,;:]+$"
    return re.sub(r"\s+", " ", re.sub(tail, "", text)).strip().casefold()


def clean_keep(keep: Any) -> list[str]:
    """The fixed lines as a list of strings; anything else (a string, a number, None, a list holding
    other things) is ignored, never an error: the reply is still sent."""
    if isinstance(keep, (list, tuple)):
        return [s for s in keep if isinstance(s, str) and s.strip()]
    return []


def keep_canon(keep: Any) -> list[str]:
    """Every fixed line, and every sentence of it, in the form `_canon` gives (multi-sentence lines
    are matched sentence by sentence and as a whole)."""
    out: list[str] = []
    for line in clean_keep(keep):
        guarded, held = protect_urls(line)
        flat = protect_abbreviations(normalise_question_marks(guarded))
        pieces = [s for _, _, s in sentence_spans(flat)]
        for piece in [*pieces, flat]:
            canon = _canon(restore_urls(piece, held))
            if len(canon) >= MIN_KEEP and canon not in out:
                out.append(canon)
    return out


def is_mandatory(sentence: str, keep: list[str]) -> bool:
    """The sentence carries content that must be said: the AI disclosure, a refusal to ask for card,
    password, code or identity details, a safety referral, or one of the fixed lines (`keep`, already
    in `keep_canon` form). It decides only which question survives when there are several."""
    if discloses_ai(sentence) or refuses_secrets(sentence) or refers_to_safety(sentence):
        return True
    canon = _canon(sentence)
    return bool(canon) and any(
        len(canon) >= MIN_KEEP and (line in canon or canon in line) for line in keep
    )


def cap_questions(text: str) -> str:
    """The post-condition: at most one question mark. Every mark but the last becomes a full stop;
    no text is dropped."""
    marks = [i for i, ch in enumerate(text) if ch in "?؟"]
    if len(marks) <= 1:
        return text
    chars = list(text)
    for i in marks[:-1]:
        chars[i] = "."
    return "".join(chars)


def _no_questions(text: str) -> str:
    """Every question mark turned into a full stop; no text is dropped."""
    return text.replace("?", ".").replace("؟", ".")


def _survivor(
    spans: list[tuple[int, int, str]], asking: list[int], held: list[str], lines: list[str]
) -> int:
    """The one question that stays a question. With a single question it is that one (never zero).
    With several it is the last one that is not mandatory, so an ordinary question gives way to nothing
    and a mandatory one is only ever demoted for an ordinary one that follows it; if every question is
    mandatory, the last of them stays a question."""
    if len(asking) == 1:
        return asking[0]
    ordinary = [i for i in asking if not is_mandatory(_original(spans[i][2], held), lines)]
    return ordinary[-1] if ordinary else asking[-1]


def _moved_last(text: str, spans: list[tuple[int, int, str]], survivor: int) -> str:
    """The surviving question moved to the end of the reply when it is not already the last sentence
    with words in it (moved, never removed)."""
    real = [i for i, (_, _, s) in enumerate(spans) if re.search(r"\w", s)]
    if not real or survivor >= real[-1]:
        return text
    start, end, sentence = spans[survivor]
    left, right = text[:start].rstrip(" \t"), text[end:]
    joined = left + (right if not right or right[0].isspace() else " " + right)
    separator = "\n\n" if "\n" in text else " "
    return joined.rstrip() + separator + sentence.strip()


def _demote(flat: str, held: list[str], lines: list[str], keep_one: bool) -> str:
    """The text with every question but the survivor turned into a statement. Nothing is dropped; the
    survivor (when `keep_one`) is last. `flat` is normalised and its links held."""
    if question_count(flat) == 0:
        return restore_urls(restore_abbreviations(flat), held)
    spans = sentence_spans(flat)
    asking = [i for i, (_, _, s) in enumerate(spans) if _ends_question(s)]
    survivor = _survivor(spans, asking, held, lines) if keep_one and asking else None
    out = flat
    for i in reversed(asking):
        if i != survivor:
            start, end, sentence = spans[i]
            out = out[:start] + _as_statement(sentence) + out[end:]
    if survivor is not None:
        out = _moved_last(out, spans, survivor)
    # a mark that sits inside a sentence, not at its end ("Which one?;"), is still a mark: with one
    # question allowed the last mark stays (never zero), without one every mark becomes a full stop
    out = cap_questions(out) if keep_one else _no_questions(out)
    return restore_urls(restore_abbreviations(out), held)


def _oversize(text: str, keep_one: bool) -> str:
    """A reply above MAX_CHARS is not parsed: a warning is logged (the length only, never the words) and
    the plain cap is applied with links held, nothing dropped. Never returned unchanged."""
    logger.warning("pi_final_question_oversize", extra={"length": len(text)})
    held: list[str] = []

    def hold(match: "re.Match[str]") -> str:
        held.append(match.group(0))
        return f"{PLACEHOLDER}{len(held) - 1}X"

    plain = URL.sub(hold, text.translate(QUESTION_MARK_VARIANTS))
    return restore_urls(cap_questions(plain) if keep_one else _no_questions(plain), held)


def _fallback(text: str, keep_one: bool) -> str:
    """When the full check fails: the question cap on the raw text (links and quotations held, so
    nothing inside them is rewritten), with nothing dropped. Never the unchanged reply."""
    try:
        guarded, held = protect_urls(text)
        flat = normalise_question_marks(guarded)
        return restore_urls(cap_questions(flat) if keep_one else _no_questions(flat), held)
    except Exception as error:  # noqa: BLE001
        logger.warning(
            "pi_final_question_fallback_failed", extra={"error_type": type(error).__name__}
        )
        return cap_questions(text) if keep_one else _no_questions(text)


def one_question_final(reply: str, keep: Any = None) -> str:
    """R-ASK-01 on the final reply: at most one question, and it is the last sentence. A question is
    demoted (its mark becomes a full stop), never dropped, so no sentence of the reply is ever lost.
    A reply with one question that is not last keeps it and moves it to the end (never zero). With
    several, the last question that is not mandatory (see `is_mandatory`) stays a question and the
    others become statements; if every question is mandatory, the last of them stays one. Links, code
    spans, "a ? b : c" expressions and quotations holding one mark are left alone. A reply longer than
    MAX_CHARS is not parsed: a warning is logged and the plain cap is applied. If the check itself
    fails, a warning is logged (the error type only) and the cap is applied to the raw text."""
    text = (reply or "").strip()
    if not text:
        return reply
    if len(text) > MAX_CHARS:
        return _oversize(text, keep_one=True)
    try:
        guarded, held = protect_urls(text)
        flat = protect_abbreviations(normalise_question_marks(guarded))
        marks = question_count(flat)
        if marks == 0 or (marks == 1 and ends_in_question(flat)):
            return reply
        return _demote(flat, held, keep_canon(keep), keep_one=True)
    except Exception as error:  # noqa: BLE001 - the reply must still be sent, and still capped
        logger.warning("pi_final_question_failed", extra={"error_type": type(error).__name__})
        return _fallback(text, keep_one=True)
