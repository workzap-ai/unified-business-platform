# ruff: noqa: E501  (one fixed line per row reads better than wrapped text)
"""Open items: nothing the owner asked disappears (platform spec v1.4, 17.7; tests HO2, HO5, A43).

Kinds: owner_question (pi could not answer it now), owner_request (a timeline, a person, a document),
pending_handoff (a person was asked to take over), promised_followup (pi said it would come back).
An item stays until it is answered or the owner drops it; no counter drops it. On the owner's
return the first line says what is still open. Staff see every open item by age, coloured against
the service level. Handoffs are read live from the request desk (`pi_staff_requests`), so the
staff view never disagrees with it.

Only written in pi_mode "brain". The wording of the system lines is in the languages of
`fixed_lines`; an Urdu chat gets Roman Urdu (the owner's rule for fixed lines), never English.
"""

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import fixed_lines, open_requests, safety, third_party
from app.modules.pi.map_edit import PROBLEMISH
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi.open_item_models import PiOpenItem
from app.shared.scope import WorkspaceScope

# Minutes allowed before an item is late (the colour on the staff view): the handoff figure is the
# spec's suggested 30 minutes; the others are half a working day and a day.
SLA_MINUTES = {
    "owner_question": 240,
    "owner_request": 240,
    "pending_handoff": 30,
    "promised_followup": 1440,
}
RETURN_AFTER_HOURS = 4
MAX_SURFACED = 2
TEXT_CAP = 300
# Q6-1: what an owner's earlier chats hand to a new chat (same workspace, same customer only).
# CARRY_DAYS is the one retention constant (subject to the P-4 retention decision).
CARRY_DAYS = 30
CARRY_MAX = 10
# An item is only taken from a chat that has been quiet this long (the same gap as the return line),
# so a chat that is still active is never raided.
CARRY_IDLE_HOURS = RETURN_AFTER_HOURS
CARRY_CANDIDATES = 200  # the most rows one carry reads; the cap of CARRY_MAX applies after them
# A staff request closes a carried question only when the team has dealt with it (never when it
# was dismissed) and it belongs to this question: it is about the same words (`tied`) and was not
# raised before the item (at most TEAM_SLACK before it: it is raised in the same turn). Time alone
# never ties it, and a request about different words does not close it even in that window: the
# question then stays open, which is the safe side.
TEAM_ANSWERED = ("answered", "published", "resolved")
TEAM_SLACK = timedelta(minutes=10)
TIE_MIN_SHARED = 2
# Common words that do not tie a request to a question (English, Roman Urdu, Urdu, Arabic).
TIE_STOP = frozenset(
    {
        "what", "your", "have", "this", "with", "about", "that", "from", "they", "them",
        "will", "would", "could", "should", "there", "their", "then", "than", "when", "where",
        "which", "while", "been", "being", "were", "just", "also", "some", "many", "much",
        "more", "most", "very", "here", "into", "over", "only", "does", "doing", "after",
        "before", "again", "still", "need", "want", "like", "make", "please", "thanks",
        "kitna", "kitne", "kitni", "kaise", "kyun", "kyon", "kabhi", "abhi", "phir", "lekin",
        "aapka", "aapki", "aapke", "mera", "meri", "mere", "hamare", "hamari", "hamara",
        "kuch", "bahut", "bohat", "kyunki", "taake", "jaise", "agar", "hain", "hoga", "hogi",
        "honge", "karna", "karne", "karen", "kijiye", "chahiye", "sakta", "sakte", "sakti",
        "batayen", "bataye", "bataiye",
        "کیا", "کیوں", "کہاں", "کون", "کتنا", "کتنی", "کتنے", "میرا", "میری", "میرے", "ہمارا",
        "لیکن", "اگر", "بھی", "کچھ", "بہت", "ہوگا", "ہوگی", "کرنا", "چاہیے", "سکتا", "سکتے",
        "بارے", "ساتھ", "لئے", "لیے",
        "ماذا", "لماذا", "كيف", "متى", "هذا", "هذه", "ذلك", "التي", "الذي", "لكن", "أريد",
        "يمكن", "بعد", "قبل", "كان", "يكون",
    }
)  # fmt: skip
CARRY_REASON = "carried_to_new_chat"

HANDOFF_STATUS = {
    "en": "Your message to the Workzap team has not been answered yet. I've asked again, and I'm "
    "here meanwhile.",
    "roman_ur": "Workzap team ko aap ki baat ka abhi jawab nahi aaya. Maine dobara kaha hai, aur "
    "main yahin hoon.",
    "ur": "Workzap ٹیم کی طرف سے آپ کی بات کا ابھی جواب نہیں آیا۔ میں نے دوبارہ کہا ہے، اور میں یہیں ہوں۔",
    "ar": "لم يصلك رد من فريق Workzap بعد. سألتهم مرة أخرى وأنا هنا في هذه الأثناء.",
    "fr": "L'équipe Workzap n'a pas encore répondu à votre message. Je l'ai relancée, et je reste ici "
    "en attendant.",
    "fa": "تیم Workzap هنوز به پیام شما پاسخ نداده است. دوباره پرسیده‌ام و در این میان همین‌جا هستم.",
    "es": "El equipo de Workzap aún no ha respondido a su mensaje. Se lo he vuelto a pedir y mientras "
    "tanto sigo aquí.",
}
# The first line on the owner's return: {text} is their own words, without question marks.
RETURN_LINE = {
    "owner_question": {
        "en": "Your earlier question is still open: “{text}”.",
        "roman_ur": "Aap ka pehle wala sawal abhi baqi hai: “{text}”.",
        "ur": "آپ کا پچھلا سوال ابھی باقی ہے: “{text}”۔",
        "ar": "سؤالك السابق ما زال مفتوحاً: “{text}”.",
        "fr": "Votre question précédente est toujours en attente : “{text}”.",
        "fa": "پرسش پیشین شما هنوز باز است: “{text}”.",
        "es": "Su pregunta anterior sigue abierta: “{text}”.",
    },
    "owner_request": {
        "en": "Your earlier request is still open: “{text}”.",
        "roman_ur": "Aap ki pehle wali darkhwast abhi baqi hai: “{text}”.",
        "ur": "آپ کی پچھلی درخواست ابھی باقی ہے: “{text}”۔",
        "ar": "طلبك السابق ما زال مفتوحاً: “{text}”.",
        "fr": "Votre demande précédente est toujours en attente : “{text}”.",
        "fa": "درخواست پیشین شما هنوز باز است: “{text}”.",
        "es": "Su petición anterior sigue abierta: “{text}”.",
    },
    "promised_followup": {
        "en": "I still owe you a follow-up on: “{text}”.",
        "roman_ur": "Mujh par aap ko is par wapas batana baqi hai: “{text}”.",
        "ur": "مجھ پر آپ کو اس بارے میں واپس بتانا باقی ہے: “{text}”۔",
        "ar": "ما زال عليّ أن أعود إليك بشأن: “{text}”.",
        "fr": "Je vous dois encore une réponse sur : “{text}”.",
        "fa": "هنوز باید درباره این به شما پاسخ بدهم: “{text}”.",
        "es": "Aún le debo una respuesta sobre: “{text}”.",
    },
}

# "pi said it would come back": the promise in each language (words, not meaning).
PROMISE = re.compile(
    r"\b(?:main\s+wapas\s+aa(?:ta|ti)\s+hoon|wapas\s+aa(?:ta|ti)\s+hoon|dobara\s+bata(?:ta|ti)"
    r"|i['’]ll\s+get\s+back\s+to\s+you|i\s+will\s+get\s+back\s+to\s+you|i['’]ll\s+come\s+back\s+to"
    r"\s+you|i['’]ll\s+follow\s+up|je\s+reviens\s+vers\s+vous|je\s+vous\s+recontacte"
    r"|le\s+respondo\s+(?:más\s+tarde|luego)|vuelvo\s+con\s+usted)\b"
    r"|سأعود\s+إليك|می[‌ ]?گردم|واپس\s+آتا\s+ہوں|واپس\s+آتی\s+ہوں",
    re.IGNORECASE,
)
# The owner drops it: a short message that leaves the matter.
DROP = re.compile(
    r"\b(?:chhor\s+do|chor\s+do|rehne\s+do|koi\s+baat\s+nahi|leave\s+it|never\s*mind|forget\s+it"
    r"|drop\s+it|laisse\s+tomber|oubliez?\s+ça|déjalo|olvídalo|olvidémoslo)\b"
    r"|اتركه|لا عليك|رہنے دو|چھوڑ دو|فراموشش کن",
    re.IGNORECASE,
)
DROP_MAX_CHARS = 60
WORDS = re.compile(r"[^\W\d_]{4,}", re.UNICODE)
QUESTION_MARKS = re.compile(r"[?？؟⁇⁈]")


def clean(text: str) -> str:
    """The owner's words as they are kept: redacted (roles, never contact details) and short. A
    third party's name is taken out where the words around it give it away (`third_party`), which
    is best effort and not a privacy boundary."""
    redacted = safety.redact_pii(text or "").text
    return " ".join(third_party.protect(redacted).split())[:TEXT_CAP]


def sla_minutes(kind: str) -> int:
    return SLA_MINUTES.get(kind, 240)


def colour(age_minutes: float, sla: int) -> str:
    """Against the service level: green until half of it, amber until all of it, then red."""
    if age_minutes >= sla:
        return "red"
    return "amber" if age_minutes >= sla / 2 else "green"


def handoff_line(language: str | None) -> str:
    return HANDOFF_STATUS[fixed_lines.table_language(language, HANDOFF_STATUS)]


def drops(said: str) -> bool:
    text = (said or "").strip()
    if not text or len(text) > DROP_MAX_CHARS or PROBLEMISH.search(text):
        return False  # "ye masla chhor do" parks a problem on the map, it does not drop an item
    return bool(DROP.search(text))


def promises(reply: str) -> bool:
    return bool(PROMISE.search(reply or ""))


def answers(question: str, reply: str) -> bool:
    """A later reply answers a question when it carries at least half of the question's own words.
    Words, not meaning: enough to close what was plainly answered."""
    wanted = {w.lower() for w in WORDS.findall(question or "")}
    if len(wanted) < 2:
        return False
    have = {w.lower() for w in WORDS.findall(reply or "")}
    return len(wanted & have) >= max(2, (len(wanted) + 1) // 2)


def tie_words(text: str) -> set[str]:
    """The words of a text that can tie it to another: 4 letters or more, none a common word."""
    return {w.lower() for w in WORDS.findall(text or "")} - TIE_STOP


def tied(text: str, question: str) -> bool:
    """A staff question belongs to an item when they share at least TIE_MIN_SHARED words that are
    not common words, and those are at least half of the item's own such words."""
    wanted = tie_words(text)
    shared = wanted & tie_words(question)
    return len(shared) >= TIE_MIN_SHARED and len(shared) * 2 >= len(wanted)


def return_line_for(items: list[dict[str, Any]], language: str | None) -> str:
    """The first line for these open items (the oldest first, at most two), in their language."""
    lines: list[str] = []
    for item in items[:MAX_SURFACED]:
        table = RETURN_LINE.get(str(item.get("kind")))
        if not table:
            continue
        text = QUESTION_MARKS.sub("", str(item.get("text") or "")).strip().rstrip(".,;:!")
        if not text:
            continue
        template = table[fixed_lines.table_language(language, table)]
        lines.append(template.format(text=text[:160]))
    return " ".join(lines)


def _mine(scope: WorkspaceScope) -> tuple[Any, ...]:
    return (
        PiOpenItem.tenant_id == scope.tenant_id,
        PiOpenItem.environment_id == scope.environment_id,
    )


async def load_for_return(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    *,
    hours_away: int,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """The open items to name first on this return (spec 17.7), oldest first. Empty when the owner
    has not been away long enough, or the item was already named on this return."""
    if hours_away < RETURN_AFTER_HOURS:
        return []
    due = (now or datetime.now(UTC)) - timedelta(hours=RETURN_AFTER_HOURS)
    rows = await _open_rows(session, scope, conversation.id)
    return [
        {"id": str(r.id), "kind": r.kind, "text": r.text}
        for r in rows
        if r.surfaced_at is None or r.surfaced_at <= due
    ]


async def _open_rows(
    session: AsyncSession, scope: WorkspaceScope, conversation_id: UUID
) -> list[PiOpenItem]:
    return list(
        await session.scalars(
            select(PiOpenItem)
            .where(
                *_mine(scope),
                PiOpenItem.conversation_id == conversation_id,
                PiOpenItem.status == "open",
            )
            .order_by(PiOpenItem.created_at)
        )
    )


class Carried(int):
    """How many items a carry moved. `complete` is False while an eligible item was left behind (its
    chat is not quiet yet, or the cap is full), so the caller tries again on a later turn."""

    complete: bool

    def __new__(cls, moved: int, complete: bool) -> "Carried":
        found = super().__new__(cls, moved)
        found.complete = complete
        return found


async def carry_into(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    *,
    now: datetime | None = None,
) -> Carried:
    """Q6-1: an owner who returns in a NEW chat finds what is still open. The open items of the
    same customer in this workspace, from other chats that have been quiet for CARRY_IDLE_HOURS, are
    moved under this conversation: newest first (ties by id), at most CARRY_MAX counting the items
    this chat already holds, none older than CARRY_DAYS, none that is answered or dropped (erased
    items no longer exist). A (kind, key) already held, or open in two old chats, moves once, and
    the cap counts after that. The brief's `open_requests` get the same entries, from the same rows.

    The rows are read with FOR UPDATE SKIP LOCKED, so two chats starting at once cannot both move
    (or double) the same row. A moved row is one row, never a copy, and it keeps its creation time, so
    the age limit is counted from when the owner asked. It is deleted by the existing erase of the
    conversation (`brain_erase`). What stays on the row: `ref_id` (the id of a staff request of this
    workspace, no words); `source_message_id`, which pointed into an earlier chat, is cleared. Never
    crosses the tenant, the environment or the customer.

    Returns how many moved; `.complete` is False when an eligible item stays behind (a chat that is
    not quiet yet, or the cap is full), so the next turn tries again. A chat with no last message time
    is never quiet. Items are read up to CARRY_CANDIDATES rows."""
    if conversation.customer_id is None:
        return Carried(0, True)
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=CARRY_DAYS)
    quiet = list(
        await session.scalars(
            select(PiConversation.id).where(
                PiConversation.tenant_id == scope.tenant_id,
                PiConversation.environment_id == scope.environment_id,
                PiConversation.customer_id == conversation.customer_id,
                PiConversation.id != conversation.id,
                PiConversation.last_message_at <= now - timedelta(hours=CARRY_IDLE_HOURS),
            )
        )
    )
    held_rows = await _open_rows(session, scope, conversation.id)
    room = CARRY_MAX - len(held_rows)
    held = {(r.kind, r.key) for r in held_rows}
    moved: list[PiOpenItem] = []
    if quiet and room > 0:
        rows = list(
            await session.scalars(
                select(PiOpenItem)
                .where(
                    *_mine(scope),
                    PiOpenItem.customer_id == conversation.customer_id,
                    PiOpenItem.conversation_id.in_(quiet),
                    PiOpenItem.status == "open",
                    PiOpenItem.created_at >= cutoff,
                )
                .order_by(PiOpenItem.created_at.desc(), PiOpenItem.id.desc())
                .limit(CARRY_CANDIDATES)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            if len(moved) >= room:
                break
            if (row.kind, row.key) in held:
                continue
            held.add((row.kind, row.key))
            row.conversation_id = conversation.id
            row.source_message_id = None
            moved.append(row)
    entries = [
        {"kind": r.key, "turns": 0}  # turns 0 marks a carried entry: named on return, not forced
        for r in moved
        if r.kind == "owner_request" and r.key in open_requests.ADDRESSES
    ]
    left = await session.scalars(
        select(PiOpenItem)
        .where(
            *_mine(scope),
            PiOpenItem.customer_id == conversation.customer_id,
            PiOpenItem.conversation_id != conversation.id,
            PiOpenItem.status == "open",
            PiOpenItem.created_at >= cutoff,
        )
        .limit(CARRY_CANDIDATES)
    )
    complete = all((r.kind, r.key) in held for r in left)
    # Last: a failure above must leave the conversation untouched (a savepoint rollback does not
    # undo an attribute set in Python, and an expired attribute reloads on the next read).
    if entries:
        brief = dict(conversation.service_brief or {})
        have = [e for e in brief.get("open_requests") or [] if isinstance(e, dict)]
        kinds = {str(e.get("kind")) for e in have}
        brief["open_requests"] = [*have, *[e for e in entries if e["kind"] not in kinds]]
        conversation.service_brief = brief
    return Carried(len(moved), complete)


async def team_answered_after(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation_id: UUID,
    since: datetime,
    *,
    customer_id: UUID | None = None,
    text: str = "",
) -> bool:
    """The team dealt with a question from the request desk after `since` (answered, published or
    resolved; a dismissed request never counts).

    Without `customer_id` it is any question of this chat, as before. With it (an item carried into
    a new chat keeps its staff request under the old conversation id) it is a question of that
    customer in this workspace that belongs to the item: about the same words as `text` (`tied`)
    and not raised before the item (more than TEAM_SLACK earlier)."""
    from app.modules.pi_saas.models import PiStaffRequest

    whose = (
        PiStaffRequest.customer_id == customer_id
        if customer_id is not None
        else PiStaffRequest.conversation_id == conversation_id
    )
    requests = await session.scalars(
        select(PiStaffRequest)
        .where(
            PiStaffRequest.tenant_id == scope.tenant_id,
            PiStaffRequest.environment_id == scope.environment_id,
            whose,
            PiStaffRequest.kind == "question",
            PiStaffRequest.status.in_(TEAM_ANSWERED),
            PiStaffRequest.resolved_at >= since,
        )
        .order_by(PiStaffRequest.created_at.desc())
        .limit(20)
    )
    for request in requests:
        if customer_id is None:
            return True
        if request.created_at >= since - TEAM_SLACK and tied(text, request.question):
            return True
    return False


def _close(row: PiOpenItem, status: str, reason: str, now: datetime) -> None:
    row.status = status
    row.closed_reason = reason
    row.closed_at = now


async def sync(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    message: PiMessage,
    *,
    reply: str,
    language: str,
    request_human: bool,
    knowledge_gaps: list[str],
    said_ids: list[str],
    now: datetime | None = None,
) -> None:
    """After a turn: close what this message or reply settled, open what it left unfinished, and
    mark the items the reply named first as named."""
    now = now or datetime.now(UTC)
    said = message.body or ""
    rows = await _open_rows(session, scope, conversation.id)
    named = set(said_ids)
    for row in rows:
        if str(row.id) in named:
            row.surfaced_at = now
    for row in rows:
        if drops(said):
            _close(row, "dropped", "owner_dropped", now)
        elif row.kind == "promised_followup":
            if not promises(reply) and answers(row.text, reply):
                _close(row, "answered", "reply_followed_up", now)
        elif row.kind == "owner_request" and row.key in open_requests.ADDRESSES:
            if open_requests.addressed(row.key, reply, request_human=request_human):
                _close(row, "answered", "reply_addressed", now)
        elif row.kind == "owner_question" and not knowledge_gaps:
            # A row carried into this chat has no source message (the move cleared it): the
            # team's answer is then looked for among the customer's questions, not this chat's.
            carried = row.source_message_id is None
            if answers(row.text, reply) or await team_answered_after(
                session,
                scope,
                conversation.id,
                row.created_at,
                customer_id=conversation.customer_id if carried else None,
                text=row.text,
            ):
                _close(row, "answered", "reply_answered", now)
    if drops(said):
        return
    still = {(r.kind, r.key) for r in rows if r.status == "open"}

    def add(kind: str, key: str, text: str) -> None:
        if (kind, key) in still:
            return
        still.add((kind, key))
        session.add(
            PiOpenItem(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                conversation_id=conversation.id,
                customer_id=conversation.customer_id,
                kind=kind,
                key=key,
                text=clean(text),
                source_message_id=message.id,
                language=language or "en",
                due_at=now + timedelta(minutes=sla_minutes(kind)),
            )
        )

    for kind in open_requests.kinds(said):
        if not open_requests.addressed(kind, reply, request_human=request_human):
            add("owner_request", kind, said)
    if knowledge_gaps and said.strip():
        add("owner_question", f"q:{message.id}", said)
    if promises(reply) and not request_human and said.strip():
        add("promised_followup", f"f:{message.id}", said)


async def age_view(
    session: AsyncSession, scope: WorkspaceScope, *, now: datetime | None = None, limit: int = 200
) -> list[dict[str, Any]]:
    """Every open item and every open handoff of the workspace, oldest first, with its age and
    the colour against its service level. Read only."""
    from app.modules.pi_saas.models import ESCALATION_KINDS, PiStaffRequest

    now = now or datetime.now(UTC)
    out: list[dict[str, Any]] = []
    rows = await session.scalars(
        select(PiOpenItem)
        .where(*_mine(scope), PiOpenItem.status == "open")
        .order_by(PiOpenItem.created_at)
        .limit(limit)
    )
    for r in rows:
        age = max(0.0, (now - r.created_at).total_seconds() / 60)
        sla = sla_minutes(r.kind)
        out.append(
            {
                "id": str(r.id),
                "kind": r.kind,
                "key": r.key,
                "text": r.text,
                "conversation_id": str(r.conversation_id),
                "customer_id": str(r.customer_id) if r.customer_id else None,
                "created_at": r.created_at.isoformat(),
                "age_minutes": round(age),
                "sla_minutes": sla,
                "colour": colour(age, sla),
            }
        )
    handoffs = await session.scalars(
        select(PiStaffRequest)
        .where(
            PiStaffRequest.tenant_id == scope.tenant_id,
            PiStaffRequest.environment_id == scope.environment_id,
            PiStaffRequest.status == "open",
            PiStaffRequest.kind.in_(ESCALATION_KINDS),
        )
        .order_by(PiStaffRequest.created_at)
        .limit(limit)
    )
    for h in handoffs:
        age = max(0.0, (now - h.created_at).total_seconds() / 60)
        sla = sla_minutes("pending_handoff")
        out.append(
            {
                "id": str(h.id),
                "kind": "pending_handoff",
                "key": str(h.kind),
                "text": clean(h.question),
                "conversation_id": str(h.conversation_id),
                "customer_id": str(h.customer_id),
                "created_at": h.created_at.isoformat(),
                "age_minutes": round(age),
                "sla_minutes": sla,
                "colour": colour(age, sla),
            }
        )
    out.sort(key=lambda e: str(e["created_at"]))
    return out[:limit]
