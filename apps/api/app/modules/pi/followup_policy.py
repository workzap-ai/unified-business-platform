# ruff: noqa: E501  (message texts read better on one line each)
"""When pi may follow up, and with what (pi Brain spec 3.9.1, R-FUP-01 to R-FUP-05).

Pure: given a chat's state, what pi has already sent and the clock, it says which follow-up is due
and when it may go out. It sends nothing. The shared ladder in followups.py does the sending and
keeps the quiet-hours, Jumu'ah and iftar checks; this module decides the *what* and the *when*.

Rules that never bend: a declined offer (S5b) is never followed up; no follow-up pressures (no
"offer expires", "last chance"); the message window is 24 hours, after that only an approved
template; "stop" ends everything (the caller checks `opted_out`).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.modules.pi import brain_config, flow, map_share

S = flow.State

WINDOW = timedelta(hours=24)

# kind -> (text in the window, template text outside it). {n} is the count of noted problems.
MESSAGES: dict[str, dict[str, str]] = {
    "silent": {
        "en": "Still here whenever you want to carry on. I've kept everything you told me.",
        "roman_ur": "Jab chahein baat jari rakhein, main yahin hoon. Aap ne jo bataya wo sab mehfooz hai.",
    },
    "paused": {
        "en": (
            "Hi, it's pi, the AI from Workzap. You asked me to check back about your {n} noted "
            "problems. Want to pick up?"
        ),
        "roman_ur": (
            "Hi, main pi hoon, Workzap ka AI. Aap ne kaha tha ke main aap ke {n} note kiye hue "
            "masail par dobara poochoon. Kya baat aage barhayein?"
        ),
    },
    "documents": {
        "en": (
            "Your solution document and quote are here whenever you're ready. Any questions, "
            "just ask."
        ),
        "roman_ur": (
            "Aap ka solution document aur quote yahan maujood hain, jab ready hon. Koi sawal ho "
            "to poochh lein."
        ),
    },
    # Decision 6 (Book 5, 6.3): value first, mentions the map, no pressure, never the Solution Box.
    "map": {
        "en": map_share.FOLLOWUP["en"],
        "roman_ur": map_share.FOLLOWUP["roman_ur"],
    },
    "kickoff_24h": {
        "en": "Reminder: your Workzap kickoff is {when}.",
        "roman_ur": "Yaad dehani: aap ka Workzap kickoff {when} ko hai.",
    },
    "kickoff_1h": {
        "en": "Reminder: your Workzap kickoff is {when}.",
        "roman_ur": "Yaad dehani: aap ka Workzap kickoff {when} ko hai.",
    },
}
# Words that would turn a follow-up into pressure (R-FUP-01). A test keeps every message clear.
PRESSURE = ("expires", "last chance", "hurry", "limited", "don't miss", "act now", "only today")


@dataclass(frozen=True)
class Chat:
    state: S
    last_inbound_at: datetime  # the person's last message
    sent: dict[str, int]  # follow-ups already sent by kind (silent, paused, documents, ...)
    last_followup_at: datetime | None = None
    paused_at: datetime | None = None  # when they said "later"
    documents_sent_at: datetime | None = None
    kickoff_at: datetime | None = None
    opted_out: bool = False
    noted_problems: int = 0
    has_map: bool = False  # a problem map has been saved for this customer
    map_sent: int = 0  # map follow-ups since the owner last wrote
    map_total: int = 0  # map follow-ups in all


@dataclass(frozen=True)
class Due:
    kind: str
    at: datetime  # the earliest moment it may go out (quiet hours etc. may push it later)
    needs_template: bool  # outside the 24-hour window: only an approved template may be sent


def _template(at: datetime, chat: Chat) -> bool:
    return at - chat.last_inbound_at >= WINDOW


def next_followup(
    chat: Chat, response_rules: dict[str, object] | None = None, now: datetime | None = None
) -> Due | None:
    """The next follow-up owed to this chat, or None. Never more than the table allows."""
    if chat.opted_out or chat.state in (S.S5B_DECLINED, S.S9B_DECLINED_QUOTE, S.X_BLOCKED):
        return None
    rules = response_rules if isinstance(response_rules, dict) else {}
    options: list[Due] = []

    def add(kind: str, at: datetime) -> None:
        options.append(Due(kind, at, _template(at, chat)))

    if chat.state in (S.S1_LISTENING, S.S2_CLARIFYING) and not chat.sent.get("silent"):
        hours = brain_config.value(rules, "followup_silence_hours")
        at = chat.last_inbound_at + timedelta(hours=hours)
        # Only inside the window: a silent person gets no template (the table has none).
        if at - chat.last_inbound_at < WINDOW:
            add("silent", at)
    if chat.state == S.X_PAUSED and chat.paused_at and not chat.sent.get("paused"):
        days = brain_config.value(rules, "paused_followup_days")
        add("paused", chat.paused_at + timedelta(days=days))
    if chat.state in (S.S7_DELIVERED, S.S8_REVIEW) and chat.documents_sent_at:
        done = chat.sent.get("documents", 0)
        if done == 0:
            first = brain_config.value(rules, "document_followup_first_days")
            add("documents", chat.documents_sent_at + timedelta(days=first))
        elif done == 1:
            second = brain_config.value(rules, "document_followup_second_days")
            add("documents", chat.documents_sent_at + timedelta(days=second))
    if chat.state == S.S12_KICKOFF and chat.kickoff_at:
        if not chat.sent.get("kickoff_24h"):
            add("kickoff_24h", chat.kickoff_at - timedelta(hours=24))
        if not chat.sent.get("kickoff_1h"):
            add("kickoff_1h", chat.kickoff_at - timedelta(hours=1))
    if not options:
        return None
    soonest = min(options, key=lambda due: due.at)
    return soonest if (now is None or soonest.at <= now) else None


# Where a quiet owner may get a map follow-up: the listening states and the map states. Not after a
# decline, not while a quote or a project is in progress (their own follow-ups cover those), not
# in an exception state (a person has the chat, an emergency, "pause", a block).
MAP_STATES = frozenset(
    {
        S.S1_LISTENING,
        S.S2_CLARIFYING,
        S.S3_NOTED,
        S.S4_SORTED_SUMMARY,
        S.S_LISTEN_THINK,
        S.S_MAP_SHARE,
        S.S_RETURN,
    }
)


def next_map_followup(chat: Chat, now: datetime | None = None) -> Due | None:
    """The next quiet-owner map follow-up (decision 6): a small number, spaced out, then stop. At
    3 and 10 days after the owner's last message, at most four over the life of the chat; always
    past the 24-hour window, so only an approved template can carry it (the sender checks the
    template and the owner's reminder consent). Nothing when they opted out."""
    if chat.opted_out or not chat.has_map or chat.state not in MAP_STATES:
        return None
    if (
        chat.map_sent >= len(map_share.FOLLOWUP_DAYS)
        or chat.map_total >= map_share.FOLLOWUP_LIFETIME
    ):
        return None
    at = chat.last_inbound_at + timedelta(days=map_share.FOLLOWUP_DAYS[chat.map_sent])
    if now is not None and at > now:
        return None
    return Due("map", at, _template(at, chat))


def text_for(kind: str, language: str | None, *, n: int = 0, when: str = "") -> str:
    table = MESSAGES[kind]
    template = table["roman_ur" if language == "roman_ur" else "en"]
    return template.format(n=n, when=when)
