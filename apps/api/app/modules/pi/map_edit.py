# ruff: noqa: E501  (one fixed line per row reads better than wrapped text)
"""Editing the map by chat (platform spec v1.4, 4.5 and test G47), brain mode only.

The owner says "ye jorr galat hai" (a link is wrong), "ye masla hal ho gaya" (solved), "ye masla chhor
do" (parked) or "pehle ye" (start here), and pi does it on the same problem and link records the
dashboard edits (`pi_customer/map_routes.py`), with a revision for each change, so the map in
WhatsApp and on the page never disagree.

What it does with the reply: a removed link replaces the reply with one line that says the link is
gone and asks the real connection (one question, the last sentence; spec 4.5). When it cannot tell
which problem or link, the reply is one question asking which. For solved, parked and ranked the
confirmation goes in front of the model's own reply. Never "noted" and never "Thanks." (spec 17.6
removes both; the v1.4 table row "thank them, remove it" is read as: be warm, do not open with the
word, see the worklog).

The words are matched in English, Roman Urdu, Urdu script, Arabic, French and Spanish. A message
that is a question ("kya ye hal ho gaya?") or a negation ("hal nahi hua") is not an edit.
"""

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import box_signals, fixed_lines, map_builder
from app.modules.pi.models import PiMessage
from app.modules.pi.problem_models import PiProblem, PiProblemLink
from app.modules.pi.problems import ProblemBook
from app.shared.scope import WorkspaceScope

UNLINK = re.compile(
    r"\b(?:jor+|jarr|jarh|link|connection|taalluq|taaluq|rishta|arrow|lien|lien|enlace|conexi[oó]n)\b"
    r".{0,30}\b(?:galat|ghalat|wrong|incorrect|false|faux|incorrecto|hata\w*|htao|remove|delete|"
    r"supprim\w*|elimin\w*|borr\w*)\b"
    r"|\b(?:galat|ghalat|wrong|incorrect|faux|incorrecto|mauvais)\b.{0,12}\b(?:jor+|link|connection|"
    r"lien|enlace|arrow)\b"
    r"|\b(?:remove|delete|hata\w*|htao|supprim\w*|elimin\w*)\b.{0,15}\b(?:link|jor+|connection|"
    r"arrow|lien|enlace)\b"
    r"|\bthese (?:two )?(?:are|r) (?:not|n['’]t) (?:connected|related|linked)\b"
    r"|\b(?:ye|yeh) (?:dono|aapas)\b.{0,20}\b(?:related|juray|jude|connected) (?:nahi|nhi)\b"
    r"|الرابط.{0,15}(?:خاطئ|غلط)|الربط.{0,15}(?:خاطئ|غلط)|(?:یہ|ی )\s*جوڑ\s*غلط|جوڑ.{0,10}غلط",
    re.IGNORECASE,
)
RESOLVE = re.compile(
    r"\b(?:hal\s+ho\s+g(?:aya|ya)|hal\s+hogaya|theek\s+ho\s+g(?:aya|ya)|khatam\s+ho\s+g(?:aya|ya)|"
    r"(?:is|has\s+been|got|now)\s+(?:solved|fixed|resolved|sorted)|(?:solved|fixed|resolved)\s+now|"
    r"est\s+r[ée]solu|est\s+r[ée]gl[ée]|ya\s+(?:est[áa]\s+)?(?:resuelto|solucionado)|"
    r"se\s+(?:resolvi[óo]|solucion[óo]))\b"
    r"|تم\s+حل|انحل\s*ت|حل\s+ہو\s+گیا",
    re.IGNORECASE,
)
PARK = re.compile(
    r"\b(?:chh?or\s+do|rehne\s+do|park\s+(?:it|this|that)|leave\s+(?:it|this|that)(?:\s+for\s+now)?|"
    r"baad\s+(?:mein|me)\s+dekh|let(?:\s+us|['’]s)\s+leave|laiss(?:e|ez)\s+(?:ça|ceci)|d[ée]jalo\s+(?:para|por)"
    r"|d[ée]jalo|apartemos)\b"
    r"|اتركه\s+الآن|اتركها|چھوڑ\s+دو",
    re.IGNORECASE,
)
# Words that mean a link on the map, never a web link: needed when no problem is named.
STRONG_LINK = re.compile(
    r"(?:jor+|jarr|jarh|taalluq|taaluq|rishta|arrow|connection)|جوڑ|الرابط|الربط"
)
# a problem, not an open question: the owner is talking about the problem
PROBLEMISH = re.compile(
    r"\b(?:masla|masle|mas'?ala|problem|issue|probl[eè]me|problema)\b|مشکل|مسئلہ|مشكلة",
    re.IGNORECASE,
)
NEGATION = re.compile(r"\b(?:not|isn['’]t|hasn['’]t|nahi|nhi|nahin|pas|no)\b", re.IGNORECASE)
NUMBERED = re.compile(r"(?:\bP\s?|#)(\d{1,4})\b", re.IGNORECASE)
WORD = re.compile(r"[^\W\d_]{4,}", re.UNICODE)
STOP = {
    "masla", "masle", "problem", "issue", "link", "galat", "ghalat", "wrong", "solved", "fixed",
    "resolved", "chhor", "chor", "pehle", "start", "first", "this", "that", "yeh", "hain", "mein",
    "hota", "hoti", "gaya", "hogaya", "leave", "park", "connection", "remove", "delete",
    "jorr", "jarr", "bhi", "sab", "kuch", "apna", "apni", "unka", "dono", "abhi", "baad", "with",
    "from", "have", "been", "your", "they", "them", "which", "there", "mera", "meri", "mere",
}  # fmt: skip

# What pi says, by action and language. {a} and {b} are the owner's own words for the problems.
LINES: dict[str, dict[str, str]] = {
    "unlink": {
        "en": "Okay, that link is off the map. What is the real connection between “{a}” and “{b}”?",
        "roman_ur": "Theek hai, woh jorr naqshe se hata diya. “{a}” aur “{b}” ka asal mein aapas mein kya taalluq hai?",
        "ar": "حسناً، أزلت هذا الرابط من الخريطة. ما العلاقة الحقيقية بين “{a}” و“{b}”؟",
        "fr": "D'accord, ce lien n'est plus sur la carte. Quel est le vrai lien entre “{a}” et “{b}” ?",
        "fa": "باشه، آن پیوند از نقشه برداشته شد. ارتباط واقعی بین “{a}” و “{b}” چیست؟",
        "es": "De acuerdo, ese enlace ya no está en el mapa. ¿Cuál es la conexión real entre “{a}” y “{b}”?",
    },
    "which_link": {
        "en": "I can take a link off once I know which. Which link do you mean, for example P1 and P2?",
        "roman_ur": "Jorr hatane se pehle mujhe pata hona chahiye ke kaun sa. Aap kaun sa jorr keh rahe hain, jaise P1 aur P2?",
        "ar": "أستطيع إزالة الرابط عندما أعرف أيّ رابط. أي رابط تقصد، مثلاً P1 وP2؟",
        "fr": "Je peux retirer un lien dès que je sais lequel. De quel lien parlez-vous, par exemple P1 et P2 ?",
        "fa": "وقتی بدانم کدام است می‌توانم پیوند را بردارم. کدام پیوند را می‌گویید، مثلاً P1 و P2؟",
        "es": "Puedo quitar un enlace en cuanto sepa cuál. ¿A qué enlace se refiere, por ejemplo P1 y P2?",
    },
    "which_problem": {
        "en": "I want to change the right one. Which problem do you mean, for example P2?",
        "roman_ur": "Main sahi wala badalna chahta hoon. Aap kaun sa masla keh rahe hain, jaise P2?",
        "ar": "أريد تغيير المشكلة الصحيحة. أي مشكلة تقصد، مثلاً P2؟",
        "fr": "Je veux modifier le bon. De quel problème parlez-vous, par exemple P2 ?",
        "fa": "می‌خواهم درست را تغییر بدهم. کدام مشکل را می‌گویید، مثلاً P2؟",
        "es": "Quiero cambiar el correcto. ¿De qué problema habla, por ejemplo P2?",
    },
    "resolve": {
        "en": "Good, “{a}” is marked as solved.",
        "roman_ur": "Achha, “{a}” hal ho gaya mark kar diya.",
        "ar": "جيد، تم وضع “{a}” كمحلول.",
        "fr": "Très bien, “{a}” est marqué comme résolu.",
        "fa": "خوب، “{a}” به‌عنوان حل‌شده علامت خورد.",
        "es": "Bien, “{a}” queda marcado como resuelto.",
    },
    "park": {
        "en": "Okay, “{a}” is parked for now.",
        "roman_ur": "Theek hai, “{a}” abhi ke liye ek taraf rakh diya.",
        "ar": "حسناً، وضعت “{a}” جانباً الآن.",
        "fr": "D'accord, “{a}” est mis de côté pour l'instant.",
        "fa": "باشه، “{a}” فعلاً کنار گذاشته شد.",
        "es": "De acuerdo, “{a}” queda aparcado por ahora.",
    },
    "rank": {
        "en": "Okay, “{a}” comes first.",
        "roman_ur": "Theek hai, “{a}” sab se pehle hai.",
        "ar": "حسناً، “{a}” يأتي أولاً.",
        "fr": "D'accord, “{a}” passe en premier.",
        "fa": "باشه، “{a}” اول است.",
        "es": "De acuerdo, “{a}” va primero.",
    },
}


@dataclass
class Edit:
    action: str  # unlink, resolve, park, rank
    outcome: str  # applied, ambiguous, nothing
    names: list[str] = field(default_factory=list)
    line: str = ""
    replaces_reply: bool = False


def wants(said: str) -> str | None:
    """The edit a message asks for, or None. A question or a negation is never an edit."""
    text = " ".join((said or "").split())
    if not text or "?" in text or "؟" in text or len(text) > 400:
        return None
    if UNLINK.search(text):
        return "unlink"
    if RESOLVE.search(text) and not NEGATION.search(text):
        return "resolve"
    if PARK.search(text) and PROBLEMISH.search(text):
        return "park"
    if box_signals.says_start_here(text) and not NEGATION.search(text):
        return "rank"
    return None


def line(action: str, language: str | None, **names: str) -> str:
    table = LINES[action]
    return table[fixed_lines.table_language(language, table)].format(**names)


def _tokens(text: str) -> set[str]:
    return {w.casefold() for w in WORD.findall(text or "")} - STOP


def _problem_tokens(p: PiProblem) -> set[str]:
    out = _tokens(p.title) | _tokens(p.title_local)
    for w in p.user_words or []:
        out |= _tokens(str(w))
    return out


def named_in(text: str, problems: list[PiProblem]) -> list[PiProblem]:
    """The problems a text points at: by number (P2, #2), else the ones whose words it shares most
    (a tie keeps all tied, so the caller can ask)."""
    wanted = {int(n) for n in NUMBERED.findall(text or "")}
    by_number = [p for p in problems if p.number in wanted]
    if by_number:
        return by_number
    words = _tokens(text)
    scored = [(len(words & _problem_tokens(p)), p) for p in problems]
    best = max((n for n, _ in scored), default=0)
    return [p for n, p in scored if n == best] if best else []


async def _last_ai_text(session: AsyncSession, scope: WorkspaceScope, message: PiMessage) -> str:
    row = await session.scalar(
        select(PiMessage.body)
        .where(
            PiMessage.tenant_id == scope.tenant_id,
            PiMessage.environment_id == scope.environment_id,
            PiMessage.conversation_id == message.conversation_id,
            PiMessage.sender_type == "ai",
            PiMessage.created_at < message.created_at,
        )
        .order_by(PiMessage.created_at.desc())
        .limit(1)
    )
    return str(row or "")


async def _target(
    session: AsyncSession, scope: WorkspaceScope, message: PiMessage, problems: list[PiProblem]
) -> list[PiProblem]:
    """The one problem "ye" means, or all candidates when it cannot be told: what the message
    names, else the only problem there is, else the one pi's last message was about."""
    said = message.body or ""
    found = named_in(said, problems)
    if found:
        return found
    if len(problems) == 1:
        return problems
    return named_in(await _last_ai_text(session, scope, message), problems)


async def _revise(book: ProblemBook, problem: PiProblem, diff: dict[str, Any], reason: str) -> None:
    problem.revision += 1
    await book._revise(problem, diff, reason, "person")  # noqa: SLF001  (same module family)


async def _set_status(book: ProblemBook, problem: PiProblem, status: str, reason: str) -> bool:
    if problem.status == status:
        return False
    diff = {"status": [problem.status, status]}
    problem.status = status
    if map_builder.PARKED_TAG in (problem.tags or []):
        problem.tags = [t for t in problem.tags if t != map_builder.PARKED_TAG]
    await _revise(book, problem, diff, reason)
    return True


async def _rank_first(book: ProblemBook, problem: PiProblem, problems: list[PiProblem]) -> bool:
    """Rank 1 for this problem; the ones already ranked move down one, in their order."""
    if box_signals.rank_of(problem.tags) == 1:
        return False
    for other in problems:
        rank = box_signals.rank_of(other.tags)
        if other.id == problem.id or rank is None:
            continue
        kept = box_signals.with_rank(
            other.tags, rank + 1 if rank + 1 <= box_signals.MAX_RANK else None
        )
        await _revise(book, other, {"tags": [other.tags, kept]}, "ranked")
        other.tags = kept
    kept = box_signals.with_rank(problem.tags, 1)
    await _revise(book, problem, {"tags": [problem.tags, kept]}, "ranked")
    problem.tags = kept
    return True


async def _unlink(
    session: AsyncSession,
    scope: WorkspaceScope,
    book: ProblemBook,
    message: PiMessage,
    problems: list[PiProblem],
    links: list[PiProblemLink],
    language: str,
) -> Edit:
    shown = map_builder.drawn_links(problems, links)
    by_id = {p.id: p for p in problems}
    named = named_in(message.body or "", problems)
    if not shown or (not named and not STRONG_LINK.search(message.body or "")):
        return Edit("unlink", "nothing")  # nothing drawn to remove, or a web link, not the map's
    if len(named) >= 2:
        ids = {p.id for p in named}
        pool = [li for li in shown if li.from_id in ids and li.to_id in ids]
    elif len(named) == 1:
        pool = [li for li in shown if named[0].id in (li.from_id, li.to_id)]
    else:
        pool = shown
    if len(pool) != 1:
        if not pool and named:
            return Edit("unlink", "nothing")  # no such link on the picture: the model answers
        return Edit("unlink", "ambiguous", line=line("which_link", language), replaces_reply=True)
    link = pool[0]
    link.status = "rejected"  # the record stays; the map does not draw it (spec 4.5)
    a, b = by_id[link.from_id], by_id[link.to_id]
    for p in (a, b):
        await _revise(book, p, {"link_removed": [str(link.id), "rejected"]}, "link_rejected")
    la, lb = map_builder.label_of(a), map_builder.label_of(b)
    return Edit(
        "unlink",
        "applied",
        names=[la, lb],
        line=line("unlink", language, a=la, b=lb),
        replaces_reply=True,
    )


async def apply(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: Any,
    message: PiMessage,
    reply: str,
    language: str,
    *,
    box_on: bool = False,
) -> tuple[str, Edit | None]:
    """Apply the edit this message asks for. Returns the reply to send (the given one when there
    is nothing to say about an edit) and what was done."""
    action = wants(message.body or "")
    customer_id: UUID | None = conversation.customer_id
    if action is None or customer_id is None:
        return reply, None
    problems, links = await map_builder.current_inputs(session, scope, customer_id)
    problems = [p for p in problems if p.merged_into is None]
    if not problems:
        return reply, None
    book = ProblemBook(session, scope, customer_id, language)
    if action == "unlink":
        edit = await _unlink(session, scope, book, message, problems, links, language)
    else:
        targets = await _target(session, scope, message, problems)
        if len(targets) != 1:
            edit = Edit(
                action,
                "ambiguous",
                line=line("which_problem", language),
                replaces_reply=True,
            )
        else:
            problem = targets[0]
            if action == "resolve":
                changed = await _set_status(book, problem, "resolved", "resolved")
            elif action == "park":
                changed = problem.status != "resolved" and await _set_status(
                    book, problem, map_builder.PARKED, "parked"
                )
            else:
                changed = await _rank_first(book, problem, problems)
                if changed and box_on:  # B3 and B4 hold, as when the owner ranks on the page
                    brief = dict(conversation.service_brief or {})
                    brief.update(map_reviewed=True, ranked=True)
                    conversation.service_brief = brief
            name = map_builder.label_of(problem)
            edit = (
                Edit(action, "applied", names=[name], line=line(action, language, a=name))
                if changed
                else Edit(action, "nothing")
            )
    await session.flush()
    if edit.outcome == "nothing" or not edit.line:
        return reply, edit
    if edit.replaces_reply:
        return edit.line, edit
    return f"{edit.line} {reply}".strip(), edit
