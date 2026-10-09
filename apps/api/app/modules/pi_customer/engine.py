"""pi Customer's live engine (runs every minute from the worker sweep).

1. Reads a chat about two minutes after the customer stops typing, so the dashboard map
   is current and nothing is sent mid-explanation.
2. Sends one visual card when something meaningful changed (a real link, or a request
   whose turn moved), at most one per chat every two hours, inside the 24-hour window.
3. Never lets a conversation go cold: when it is the customer's turn, a nudge quoting
   the exact open question at about 20 hours (still free-form), then the business's
   approved templates on days 3, 7 and 14; when it is the team's turn, alerts to the
   team at 12, 24 and 48 hours and one status line to the customer.

Quiet hours, Friday prayers, "waiting on someone else", STOP and a person having just
replied all stop pi. Everything it does is logged on the brief ("nudges").
"""

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.modules.notifications.service import notify
from app.modules.pi.configuration import settings_row
from app.modules.pi.followups import quiet_until
from app.modules.pi.models import PiConversation, PiMessage, WhatsAppConnection
from app.modules.pi.service import PiService
from app.modules.pi_customer import service
from app.modules.pi_customer.cards import card_token, card_url

logger = logging.getLogger("platform")

READ_AFTER = timedelta(minutes=2)
READ_WITHIN = timedelta(minutes=45)
CARD_GAP = timedelta(hours=2)
# The customer asked for their map: answered at once, at most every 10 minutes.
ASKED_GAP = timedelta(minutes=10)
MAP_ASK = re.compile(
    r"\b(?:problem\s*map|my\s+map|the\s+map|map\s+(?:dikhao|dikha\s*do|bhejo|bhej\s*do|send|show)"
    r"|naqsh[ae]?|naksh[ae]?)\b"
    r"|\b(?:progress|status|journey|safar)\b.{0,24}\b(?:dikhao|dikha\s*do|bhejo|bhej\s*do|show|send)\b"
    r"|\b(?:show|send)\b.{0,24}\b(?:progress|status|journey|map)\b",
    re.IGNORECASE,
)
NUDGE_AT, WINDOW = timedelta(hours=20), timedelta(hours=23, minutes=30)
LADDER = (("day3", timedelta(days=3)), ("day7", timedelta(days=7)), ("day14", timedelta(days=14)))
TEMPLATE_GAP = timedelta(hours=72)
MAX_TOUCHES = 4
HUMAN_QUIET = timedelta(hours=12)
SLA_HOURS = ((12, "info"), (24, "warning"), (48, "critical"))
STOP = re.compile(
    r"\b(?:stop|unsubscribe|band karo|band kar do|band kardo|mat bhejo|mat bhejna|"
    r"no more messages|don'?t message)\b",
    re.IGNORECASE,
)


MAP_NOTE = (
    "The customer is asking for their Problem Map: pi's picture of all their requests "
    "and how they connect (NOT a geographic map or a location). pi sends it as an image "
    "in this chat within a minute. Reply with ONE short line in their language saying it "
    "is on its way. Do not ask about any location, area or address."
)


def map_request_note(whatsapp_config: dict[str, Any] | None, settings: Any, text: str) -> str:
    """What pi's reply needs to know when the customer asks for their map, or ""."""
    config = whatsapp_config or {}
    if (
        not text
        or not MAP_ASK.search(text)
        or not service.portal_on(config)
        or config.get("visual_cards", True) is False
        or not str(getattr(settings, "pi_app_public_url", "")).startswith("http")
    ):
        return ""
    return MAP_NOTE


def urdu(language: str) -> bool:
    return language in {"roman_ur", "ur", "hi"}


def norm_language(language: str | None) -> str:
    """The three languages pi's own WhatsApp lines are written in."""
    if urdu(str(language or "")):
        return "roman_ur"
    return "ar" if language == "ar" else "en"


def wa_language(latest: str, conversation: PiConversation) -> str:
    """Strictly the language of the customer's latest WhatsApp message (the same
    detector pi's replies use); the chat's last known language when it is unclear."""
    from app.modules.pi.language import detect_language

    return norm_language(detect_language(latest) or conversation.language)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n != 1 else ''}"


TEXT: dict[str, dict[str, Any]] = {
    "en": {
        "here": "Here is your problem map.",
        "glance": lambda n, m: (
            f"Your {_plural(n, 'request')} at a glance" + (f", {m} connected." if m else ".")
        ),
        "found": lambda n, reason: f"pi found {_plural(n, 'connection')}. {reason}.",
        "noted": lambda title: f'pi noted "{title}".',
        "you": "You: ",
        "next": "Next: ",
        "nudge": lambda title, q: f'Quick one on "{title}": {q}',
        "status": lambda title, due: (
            f'The team is working on "{title}". You\'ll get an update here by {due}.'
        ),
    },
    "roman_ur": {
        "here": "Yeh raha aap ka problem map.",
        "glance": lambda n, m: (
            f"Aap ke {n} masle ek nazar mein" + (f", {m} aapas mein jude hue." if m else ".")
        ),
        "found": lambda n, reason: f"pi ne aap ke requests mein {n} connection dhoonde. {reason}.",
        "noted": lambda title: f'pi ne note kiya: "{title}".',
        "you": "Aap: ",
        "next": "Agla qadam: ",
        "nudge": lambda title, q: f'Ek chhota sa sawal "{title}" ke baare mein: {q}',
        "status": lambda title, due: (
            f'"{title}" pe team kaam kar rahi hai. Update {due} tak yahin milega.'
        ),
    },
    "ar": {
        "here": "هذه خريطة طلباتك.",
        "glance": lambda n, m: f"{n} طلبات في لمحة" + (f"، {m} مترابطة." if m else "."),
        "found": lambda n, reason: f"وجد pi {n} روابط. {reason}.",
        "noted": lambda title: f'سجّل pi: "{title}".',
        "you": "أنت: ",
        "next": "الخطوة التالية: ",
        "nudge": lambda title, q: f'سؤال سريع حول "{title}": {q}',
        "status": lambda title, due: f'الفريق يعمل على "{title}". ستصلك تحديثات هنا بحلول {due}.',
    },
}


def prayer_or_quiet(policy: Any, now: datetime | None = None) -> bool:
    """No sends at night (business quiet hours) or during Friday prayers (12:30-14:30)."""
    from app.modules.pi.policy import zone

    config = policy.whatsapp_config or {}
    if quiet_until(
        policy.timezone, int(config.get("quiet_start", 21)), int(config.get("quiet_end", 9)), now
    ):
        return True
    local = (now or datetime.now(UTC)).astimezone(zone(policy.timezone))
    minutes = local.hour * 60 + local.minute
    return local.weekday() == 4 and 12 * 60 + 30 <= minutes < 14 * 60 + 30


async def sweep_customer_journeys(ctx: dict[str, Any]) -> None:
    from app.modules.pi.runtime import enqueue_sends

    outgoing: list[str] = []
    try:
        outgoing += await read_quiet_chats(ctx)
    except Exception:  # noqa: BLE001 - one bad chat must not stop the ladder
        logger.warning("pi_customer_read_failed")
    try:
        outgoing += await run_ladder(ctx)
    except Exception:  # noqa: BLE001
        logger.warning("pi_customer_ladder_failed")
    await enqueue_sends(ctx, outgoing)


# --------------------------------------------------------------------------- reading


async def read_quiet_chats(ctx: dict[str, Any]) -> list[str]:
    """Chats whose customer stopped writing 2-45 minutes ago and pi hasn't read since,
    plus any chat whose customer just asked to see their map (answered within a minute)."""
    from app.modules.pi.runtime import system_scope
    from app.modules.pi_customer.models import CustomerPrefs

    now = datetime.now(UTC)
    outgoing: list[str] = []
    async with ctx["sessions"]() as session:
        rows = await session.execute(
            select(PiConversation, WhatsAppConnection)
            .join(
                WhatsAppConnection,
                (WhatsAppConnection.id == PiConversation.connection_id)
                & (WhatsAppConnection.tenant_id == PiConversation.tenant_id),
            )
            .where(
                PiConversation.status == "open",
                PiConversation.last_inbound_at >= now - READ_WITHIN,
            )
            .order_by(PiConversation.last_inbound_at)
            .limit(20)
        )
        done = 0
        for conversation, connection in rows.all():
            if done >= 4:
                break
            brief = conversation.service_brief or {}
            inbound_at = conversation.last_inbound_at.isoformat()
            latest = await _last_inbound_text(session, conversation)
            asked = brief.get("map_answered_for") != inbound_at and bool(MAP_ASK.search(latest))
            quiet = conversation.last_inbound_at <= now - READ_AFTER
            if not quiet and not asked:
                continue  # never mid-explanation
            cached = brief.get("customer_issues")
            fresh = isinstance(cached, dict) and cached.get("at") == (
                conversation.last_message_at.isoformat()
            )
            if fresh and not asked:
                continue
            scope = await system_scope(session, connection)
            if scope is None:
                continue
            policy = await settings_row(session, scope)
            if not service.portal_on(policy.whatsapp_config):
                continue
            prefs = await session.scalar(
                select(CustomerPrefs).where(CustomerPrefs.phone == conversation.contact_wa_id)
            )
            report = (
                cached
                if fresh and isinstance(cached, dict)
                else await service.analyse(
                    session,
                    ctx["settings"],
                    ctx["http"],
                    ctx.get("sessions"),
                    conversation,
                    connection,
                    (connection.display_name or "").strip() or "the business",
                    prefs.language if prefs else "auto",
                )
            )
            done += 1
            if report and (asked or report.get("new_events")):
                await session.refresh(conversation)
                card = await queue_card(
                    session,
                    scope,
                    policy,
                    conversation,
                    report,
                    settings=ctx["settings"],
                    asked=asked,
                    language=wa_language(latest, conversation),
                )
                if card:
                    outgoing.append(card)
                if asked:
                    conversation.service_brief = {
                        **(conversation.service_brief or {}),
                        "map_answered_for": inbound_at,
                    }
        await session.commit()
    return outgoing


def _open(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [i for i in issues if i.get("stage") not in ("live", "closed", "paused")]


def _map_caption(report: dict[str, Any], lang: str, lead: str = "") -> str:
    issues = _open(report.get("issues") or []) or list(report.get("issues") or [])
    links = [x for x in report.get("links") or [] if x.get("status") in ("auto", "confirmed")]
    return f"{lead} {TEXT[lang]['glance'](len(issues), len(links))}".strip()


def _journey_caption(issue: dict[str, Any], lang: str) -> str:
    if issue.get("ball_with") == "client" and issue.get("open_question"):
        what, who = issue["open_question"], TEXT[lang]["you"]
    else:
        what, who = str(issue.get("next_step") or ""), TEXT[lang]["next"]
    return f'"{issue["title"]}"\n{who}{what}'.strip()


def pick_card(
    report: dict[str, Any], asked: bool = False, language: str | None = None
) -> tuple[str, int, str] | None:
    """(kind, request index, caption) for the most useful card, or None. The caption is
    in ``language`` (the customer's latest message), else the report's language.

    - The customer asked for their map: the map (or the journey, with one request).
    - A real link with a saving: the map, with the reason.
    - A request moved on: its journey card (the brief's "first card to send").
    - A new request when three or more are open: the map, so they see the whole picture.
    "Noted" alone, or a map of one or two dots, never gets a card on its own."""
    events = report.get("new_events") or []
    issues = report.get("issues") or []
    lang = norm_language(language or str(report.get("language") or ""))
    words = TEXT[lang]
    links = [x for x in report.get("links") or [] if x.get("status") in ("auto", "confirmed")]
    if asked and issues:
        if len(issues) == 1:
            return "journey", 0, _journey_caption(issues[0], lang)
        return "map", 0, _map_caption(report, lang, words["here"])
    announced = [e for e in events if e.get("kind") == "link.found" and e.get("announce")]
    if announced and links:
        reason = str(announced[-1].get("detail") or "").rstrip(".")
        return "map", 0, words["found"](len(links), reason).replace(" .", "").strip()
    for event in reversed(events):
        if event.get("kind") != "stage.changed" or event.get("to") in ("noted", "live", "closed"):
            continue
        index = next(
            (
                i
                for i, issue in enumerate(issues)
                if service.norm_title(issue["title"]) == service.norm_title(event["title"])
            ),
            None,
        )
        if index is not None:
            return "journey", index, _journey_caption(issues[index], lang)
    noted = [e for e in events if e.get("kind") == "problem.noted"]
    if noted and len(_open(issues)) >= 3:
        lead = words["noted"](str(noted[-1].get("title") or ""))
        return "map", 0, _map_caption(report, lang, lead)
    return None


async def queue_card(
    session: Any,
    scope: Any,
    policy: Any,
    conversation: PiConversation,
    report: dict[str, Any],
    *,
    settings: Any = None,
    asked: bool = False,
    language: str | None = None,
) -> str | None:
    """Queue one card image (inside the 24-hour window). An asked-for map goes out at
    once (they are writing right now); others wait two hours between cards and respect
    quiet hours and Friday prayers."""
    if settings is None:  # the worker passes its own settings
        from app.core.config import get_settings

        settings = get_settings()
    if not settings.pi_app_public_url.startswith("http"):
        # WhatsApp fetches the picture from the pi app: without its public address
        # there is nothing it could open.
        logger.warning("pi_customer_card_no_public_url")
        return None
    config = policy.whatsapp_config or {}
    brief = conversation.service_brief or {}
    now = datetime.now(UTC)
    last = brief.get("cards_last_at")
    gap = ASKED_GAP if asked else CARD_GAP
    if (
        config.get("visual_cards", True) is False
        or conversation.mode != "ai"
        or not conversation.last_inbound_at
        or now - conversation.last_inbound_at > timedelta(hours=23)
        or (last and now - datetime.fromisoformat(last) < gap)
        or (not asked and prayer_or_quiet(policy, now))
    ):
        return None
    lang = norm_language(language or str(report.get("language") or ""))
    choice = pick_card(report, asked=asked, language=lang)
    if choice is None:
        return None
    kind, index, caption = choice
    link = card_url(settings, card_token(settings, conversation.id, kind, index, lang))
    dashboard = f"{settings.pi_app_public_url.rstrip('/')}/customer"
    caption = f"{caption}\n{dashboard}"
    pi = PiService(session, scope)
    key = (
        f"pi-card:{conversation.id}:ask:{conversation.last_inbound_at.isoformat()}"
        if asked
        else f"pi-card:{conversation.id}:{report['at']}"
    )
    if await pi.messages.find(PiMessage.idempotency_key == key):
        return None
    message = await pi.messages.add(
        pi.messages.new(
            conversation_id=conversation.id,
            direction="outbound",
            sender_type="ai",
            agent_key="requirement",
            body=caption[:1000],
            status="queued",
            idempotency_key=key,
            media={"image": link, "card": kind},
        )
    )
    conversation.service_brief = {**brief, "cards_last_at": now.isoformat()}
    return str(message.id)


# ---------------------------------------------------------------------------- ladder


def _log(conversation: PiConversation, entry: dict[str, Any]) -> None:
    brief = dict(conversation.service_brief or {})
    brief["nudges"] = [*(brief.get("nudges") or []), entry][-40:]
    conversation.service_brief = brief


def _sent(brief: dict[str, Any], since: str, step: str) -> bool:
    return any(n.get("since") == since and n.get("step") == step for n in brief.get("nudges") or [])


async def run_ladder(ctx: dict[str, Any]) -> list[str]:
    from app.modules.pi.runtime import system_scope

    now = datetime.now(UTC)
    outgoing: list[str] = []
    async with ctx["sessions"]() as session:
        conversations = await session.scalars(
            select(PiConversation)
            .where(
                PiConversation.status == "open",
                PiConversation.last_message_at >= now - timedelta(days=16),
            )
            .order_by(PiConversation.last_message_at.desc())
            .limit(300)
        )
        for conversation in list(conversations):
            brief = conversation.service_brief or {}
            report = brief.get("customer_issues")
            if not isinstance(report, dict) or not report.get("issues"):
                continue
            connection = await session.get(WhatsAppConnection, conversation.connection_id)
            scope = await system_scope(session, connection) if connection else None
            if scope is None:
                continue
            policy = await settings_row(session, scope)
            if (
                not service.portal_on(policy.whatsapp_config)
                or (policy.whatsapp_config or {}).get("follow_up_ladder", True) is False
            ):
                continue
            issues = report["issues"]
            waiting = report.get("waiting") or {}
            client = [
                i for i in issues if i.get("ball_with") == "client" and i.get("open_question")
            ]
            team = [i for i in issues if i.get("ball_with") == "team"]
            if client and waiting.get("client"):
                queued = await nudge_customer(
                    session, scope, policy, conversation, client[0], waiting["client"], now
                )
                if queued:
                    outgoing.append(queued)
            if team and waiting.get("team"):
                queued = await alert_team(
                    session, scope, policy, conversation, team[0], waiting["team"], now
                )
                if queued:
                    outgoing.append(queued)
        await session.commit()
    return outgoing


async def _human_recently(session: Any, conversation: PiConversation, now: datetime) -> bool:
    last = await session.scalar(
        select(PiMessage.created_at)
        .where(
            PiMessage.tenant_id == conversation.tenant_id,
            PiMessage.environment_id == conversation.environment_id,
            PiMessage.conversation_id == conversation.id,
            PiMessage.sender_type == "human",
        )
        .order_by(PiMessage.created_at.desc())
        .limit(1)
    )
    return bool(last and now - last < HUMAN_QUIET)


async def _last_inbound_text(session: Any, conversation: PiConversation) -> str:
    body = await session.scalar(
        select(PiMessage.body)
        .where(
            PiMessage.tenant_id == conversation.tenant_id,
            PiMessage.environment_id == conversation.environment_id,
            PiMessage.conversation_id == conversation.id,
            PiMessage.direction == "inbound",
        )
        .order_by(PiMessage.created_at.desc())
        .limit(1)
    )
    return body or ""


async def nudge_customer(
    session: Any,
    scope: Any,
    policy: Any,
    conversation: PiConversation,
    issue: dict[str, Any],
    since_raw: str,
    now: datetime,
) -> str | None:
    """The customer's turn: one nudge at ~20h (free-form, quoting the open question),
    then the business's approved templates on days 3, 7 and 14. Four touches at most."""
    brief = conversation.service_brief or {}
    since = datetime.fromisoformat(since_raw)
    waited = now - since
    paused = brief.get("customer_waiting_until")
    if (
        conversation.mode != "ai"
        or brief.get("reminder_consent") == "declined"
        or (paused and datetime.fromisoformat(paused) > now)
        or waited < NUDGE_AT
        or sum(1 for n in brief.get("nudges") or [] if n.get("since") == since_raw) >= MAX_TOUCHES
    ):
        return None
    latest = await _last_inbound_text(session, conversation)
    if STOP.search(latest):
        conversation.service_brief = {**brief, "reminder_consent": "declined"}
        return None
    if prayer_or_quiet(policy, now) or await _human_recently(session, conversation, now):
        return None
    language = wa_language(latest, conversation)
    pi = PiService(session, scope)
    window_open = bool(conversation.last_inbound_at and now - conversation.last_inbound_at < WINDOW)
    if waited < WINDOW and window_open and not _sent(brief, since_raw, "nudge1"):
        title, question = issue["title"], issue["open_question"]
        body = TEXT[language]["nudge"](title, question)
        key = f"pi-nudge:{conversation.id}:{since_raw}:1"
        if await pi.messages.find(PiMessage.idempotency_key == key):
            return None
        message = await pi.messages.add(
            pi.messages.new(
                conversation_id=conversation.id,
                direction="outbound",
                sender_type="ai",
                agent_key="requirement",
                body=body,
                status="queued",
                idempotency_key=key,
                media={"nudge": "nudge1"},
            )
        )
        _log(conversation, {"at": now.isoformat(), "since": since_raw, "step": "nudge1"})
        return str(message.id)
    # After the window: approved templates only, with consent, one per 72 hours.
    step = next(
        (
            name
            for name, after in reversed(LADDER)
            if waited >= after and not _sent(brief, since_raw, name)
        ),
        None,
    )
    if step is None or brief.get("reminder_consent") != "granted":
        return None
    last_template = max(
        (n["at"] for n in brief.get("nudges") or [] if n.get("step", "").startswith("day")),
        default=None,
    )
    if last_template and now - datetime.fromisoformat(last_template) < TEMPLATE_GAP:
        return None
    templates = (policy.whatsapp_config or {}).get("ladder_templates", {}).get(
        language or "en"
    ) or {}
    template = templates.get(step)
    if not template:
        await notify(
            session,
            scope,
            "pi.ladder_template_missing",
            "pi needs an approved WhatsApp template for follow-ups",
            f"Add a {language or 'en'} '{step}' template under pi's follow-up settings.",
            permission="pi.read",
            dedupe_key=f"pi-ladder-missing:{scope.tenant_id}:{language}:{step}",
        )
        _log(
            conversation,
            {"at": now.isoformat(), "since": since_raw, "step": step, "status": "no_template"},
        )
        return None
    key = f"pi-nudge:{conversation.id}:{since_raw}:{step}"
    if await pi.messages.find(PiMessage.idempotency_key == key):
        return None
    message = await pi.messages.add(
        pi.messages.new(
            conversation_id=conversation.id,
            direction="outbound",
            sender_type="ai",
            agent_key="requirement",
            body=f"Follow-up template queued: {template.get('name', step)}",
            status="queued",
            idempotency_key=key,
            media={"ladder": {"template": template, "step": step}},
        )
    )
    _log(conversation, {"at": now.isoformat(), "since": since_raw, "step": step})
    return str(message.id)


async def alert_team(
    session: Any,
    scope: Any,
    policy: Any,
    conversation: PiConversation,
    issue: dict[str, Any],
    since_raw: str,
    now: datetime,
) -> str | None:
    """The team's turn: alerts at 12, 24 and 48 hours without a reply from a person, and
    at 12 hours one status line to the customer so they never feel ignored."""
    since = datetime.fromisoformat(since_raw)
    replied = await session.scalar(
        select(PiMessage.id).where(
            PiMessage.tenant_id == conversation.tenant_id,
            PiMessage.environment_id == conversation.environment_id,
            PiMessage.conversation_id == conversation.id,
            PiMessage.sender_type == "human",
            PiMessage.created_at > since,
        )
    )
    if replied:
        return None
    waited = now - since
    for hours, severity in SLA_HOURS:
        if waited >= timedelta(hours=hours):
            await notify(
                session,
                scope,
                "pi.team_sla",
                f"A customer has waited {hours}h for the team",
                f'"{issue["title"]}": {issue.get("next_step") or "the team owes an update"}.',
                link=f"/pi/inbox?conversation={conversation.id}",
                permission="pi.handoffs.manage",
                severity=severity,
                dedupe_key=f"pi-sla:{conversation.id}:{since_raw}:{hours}",
            )
    brief = conversation.service_brief or {}
    if (
        waited < timedelta(hours=12)
        or _sent(brief, since_raw, "status")
        or not conversation.last_inbound_at
        or now - conversation.last_inbound_at > WINDOW
        or brief.get("reminder_consent") == "declined"
        or prayer_or_quiet(policy, now)
    ):
        return None
    hours = await service.team_update_hours(session, conversation)
    due = service.next_update_by(since, hours).strftime("%a %d %b")
    language = wa_language(await _last_inbound_text(session, conversation), conversation)
    body = TEXT[language]["status"](issue["title"], due)
    pi = PiService(session, scope)
    key = f"pi-status:{conversation.id}:{since_raw}"
    if await pi.messages.find(PiMessage.idempotency_key == key):
        return None
    message = await pi.messages.add(
        pi.messages.new(
            conversation_id=conversation.id,
            direction="outbound",
            sender_type="ai",
            agent_key="requirement",
            body=body,
            status="queued",
            idempotency_key=key,
            media={"nudge": "status"},
        )
    )
    _log(conversation, {"at": now.isoformat(), "since": since_raw, "step": "status"})
    return str(message.id)
