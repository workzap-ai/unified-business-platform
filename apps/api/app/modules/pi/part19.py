# ruff: noqa: E501  (phrase banks read better one alternative per line)
"""Platform spec v1.6, Part 19 (Engagement Engine v2.5): buying signals, direct questions, what
counts as a problem, the owner's number, no dead ends, summaries. Evidence: Live Audit 6 (Book 8),
the Artwing Studios chat of 30 October.

Pure functions. Nothing here reads the database or sends a message; the caller supplies the context
and acts on the answer. `system_ask` holds the R3 ask itself (19.2 "aap ye sab kar denge").
"""

import re
from typing import Any

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
    if buying_signal(said, 0) == "R1":
        return True  # a price or quote ask goes to the quote (19.2), never to a summary
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
    r"\bkitna\s+(?:kharcha|kharch|lagega|lagay\s?ga|paisa|cost)\b(?!\s+(?:time|waqt|din|hafte|mahine))"
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


def statement_only(reply: str) -> str:
    """The reply without its questions (R-ASK-01): used before the offer is appended, so the offer
    is the only question of the message and it is last."""
    lines: list[str] = []
    for line in (reply or "").splitlines():
        parts = re.split(r"(?<=[.!?؟])\s+", line.strip())
        kept = [p for p in parts if p and not p.endswith(("?", "؟"))]
        if kept:
            lines.append(" ".join(kept))
    return "\n".join(lines).strip()
