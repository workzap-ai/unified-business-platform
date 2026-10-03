"""pi product help: setup guides the pi Assistant answers from, managed by the operator.

Built-in guides ship with the code. Operators can edit any guide (an override with the
same id), add their own, or hide one, from the Owner OS console. Their changes live in
``pi_platform_state`` under one key, so no migration is needed. Guides are platform
content, never business data: every business sees the same help.
"""

import re
from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi_saas.models import PiPlatformState
from app.shared.errors import BusinessRuleViolation, ResourceNotFound

KEY = "assistant_help"
PI_PAGES = (
    "/home",
    "/inbox",
    "/customers",
    "/customers/campaigns",
    "/my-pi",
    "/my-pi/behaviour",
    "/my-pi/follow-ups",
    "/my-pi/knowledge",
    "/my-pi/settings",
    "/my-pi/test",
    "/my-pi/tools",
    "/notifications",
    "/settings",
    "/settings/billing",
    "/settings/business",
    "/settings/business-review",
    "/settings/notifications",
    "/settings/payments",
    "/settings/setup",
    "/settings/team",
    "/settings/whatsapp",
    "/setup",
)
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{1,59}$")]


class Article(BaseModel):
    id: Slug
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=6000)]
    tags: list[Annotated[str, StringConstraints(max_length=40)]] = Field(
        default_factory=list, max_length=12
    )
    page: str | None = None  # a Pi app page the guide points to
    builtin: bool = False
    hidden: bool = False
    updated_by: str | None = None
    updated_at: datetime | None = None


class ArticleInput(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=6000)]
    tags: list[Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]] = Field(
        default_factory=list, max_length=12
    )
    page: str | None = None


def _builtin(id: str, title: str, page: str, tags: str, body: str) -> Article:
    return Article(
        id=id, title=title, page=page, tags=tags.split(), body=" ".join(body.split()), builtin=True
    )


BUILTIN: tuple[Article, ...] = (
    _builtin(
        "connect-whatsapp",
        "Connect your WhatsApp number",
        "/settings/whatsapp",
        "whatsapp number connect kapso setup pool",
        """pi answers your customers on WhatsApp, so a connected number comes first. Open
        Settings → WhatsApp. You can connect your own WhatsApp Business number through the
        guided Meta sign-up, or pick a ready number from the list we offer. When the number
        shows as connected, send it a test message from another phone. If the page says your
        business is waiting for review, finish the business review first.""",
    ),
    _builtin(
        "business-review",
        "Business review and approval",
        "/settings/business-review",
        "review approval verify business pending",
        """Before pi can message customers, we review your business details. Open Settings →
        Business review, complete every field and submit. You'll be notified when it's
        approved; until then WhatsApp sending stays off. If something was rejected, the page
        shows the reason so you can fix it and submit again.""",
    ),
    _builtin(
        "setup-checklist",
        "Your setup checklist",
        "/settings/setup",
        "setup checklist start onboarding ready",
        """Settings → Setup lists everything pi needs and what is still missing: WhatsApp
        number, business details, what you sell, knowledge, and optional tools like
        calendars or payments. Each item links to the page that fixes it. pi goes live once
        the required items are done. Use 'Help me set up' if you'd like our team to assist.""",
    ),
    _builtin(
        "teach-pi",
        "Teach pi about your business",
        "/my-pi/knowledge",
        "knowledge teach train faq documents upload files prices",
        """pi only answers from what you teach it. Open My pi → Knowledge to add answers,
        policies, prices and opening hours, or upload documents such as a price list or menu.
        Keep each entry short and specific. When a customer asks something pi doesn't know,
        it hands the chat to your team instead of guessing, and the question shows up so you
        can teach the answer.""",
    ),
    _builtin(
        "test-pi",
        "Test pi before customers see it",
        "/my-pi/test",
        "test playground try preview",
        """My pi → Test lets you chat with pi as a customer would, using your real knowledge
        and settings, without sending anything on WhatsApp. Try common questions, prices and
        a booking request, then adjust knowledge or behaviour and test again.""",
    ),
    _builtin(
        "pi-behaviour",
        "Change how pi talks and when it hands over",
        "/my-pi/behaviour",
        "behaviour tone language handoff approval rules hours",
        """My pi → Behaviour controls pi's tone, languages, business hours and when it should
        hand a chat to a person. You can require approval before pi sends certain replies;
        those drafts wait in the Inbox for a team member to approve or edit.""",
    ),
    _builtin(
        "inbox-handoffs",
        "Inbox, handoffs and approvals",
        "/inbox",
        "inbox chats conversations handoff takeover approve reply assign",
        """The Inbox shows every WhatsApp conversation you're allowed to see. When pi hands a
        chat over, it appears as waiting for the team: open it, read pi's summary, and reply
        or take over. Drafts that need approval are listed there too. Owners and managers can
        assign chats to team members; members only see chats assigned to them.""",
    ),
    _builtin(
        "team-roles",
        "Invite your team and choose roles",
        "/settings/team",
        "team invite member roles permissions owner manager staff",
        """Settings → Team lets you invite people by email and choose a role. Owners and admins
        manage everything. Managers run day-to-day work and see all chats and reports.
        Members handle the chats assigned to them. Viewers can look but not change anything.
        Billing users only manage the plan and invoices.""",
    ),
    _builtin(
        "tools-connectors",
        "Connect calendars, stores and other tools",
        "/my-pi/tools",
        "tools connect google calendar shopify booking store integration",
        """My pi → Tools connects pi to your other systems, for example Google Calendar so pi
        can offer real booking slots, or your Shopify store so it can answer about products
        and orders. Each business connects its own accounts; you can disconnect at any time.""",
    ),
    _builtin(
        "follow-ups",
        "Automatic follow-ups",
        "/my-pi/follow-ups",
        "follow up reminder remarketing nudge",
        """My pi → Follow-ups lets pi check back with customers who went quiet, for example
        after a quote. Choose when follow-ups are sent and what they say. pi respects
        WhatsApp's messaging window and your customers' consent.""",
    ),
    _builtin(
        "campaigns",
        "Send WhatsApp campaigns",
        "/customers/campaigns",
        "campaign broadcast bulk marketing template consent",
        """Customers → Campaigns sends an approved WhatsApp template to a tagged group of
        customers who agreed to hear from you. Campaigns respect quiet hours and a daily
        limit, and show delivery and reply results afterwards.""",
    ),
    _builtin(
        "getting-paid",
        "Take payments from customers",
        "/settings/payments",
        "payments paid card bank transfer wallet cash jazzcash easypaisa stripe link",
        """Settings → Payments lets pi send payment requests. Card payments use your connected
        Stripe account. Bank transfer, mobile wallet and cash payments are marked paid only
        after someone on your team checks the proof; pi never confirms those on its own.""",
    ),
    _builtin(
        "plan-billing",
        "Your plan, usage and invoices",
        "/settings/billing",
        "plan billing invoice usage limit upgrade subscription trial",
        """Settings → Billing shows your plan, what's included, how much you've used this
        month and your invoices. When you get close to a limit you'll see a notice; upgrade
        there if you need more conversations or messages.""",
    ),
    _builtin(
        "notifications-digest",
        "Notifications and the weekly summary",
        "/settings/notifications",
        "notifications alerts email weekly digest summary",
        """Settings → Notifications chooses which alerts you get, such as chats waiting for
        the team or payments to verify, and whether you get the weekly summary email with
        conversations, enquiries and how much pi handled on its own.""",
    ),
    _builtin(
        "customer-portal",
        "Let customers see their own chats",
        "/settings",
        "customer portal app otp login history",
        """You can give customers a simple page where they sign in with a code sent to their
        WhatsApp and see their own conversations with your business. Turn it on and share
        the link from your business settings.""",
    ),
)


def _now() -> datetime:
    return datetime.now(UTC)


async def _state(session: AsyncSession, *, lock: bool = False) -> PiPlatformState:
    row = await session.get(PiPlatformState, KEY, with_for_update=lock)
    if row is None:
        row = PiPlatformState(key=KEY, value={"articles": {}, "hidden": []})
        session.add(row)
        await session.flush()
    return row


async def articles(session: AsyncSession, *, include_hidden: bool = False) -> list[Article]:
    row = await session.get(PiPlatformState, KEY)
    stored: dict[str, Any] = (row.value or {}).get("articles", {}) if row else {}
    hidden = set((row.value or {}).get("hidden", [])) if row else set()
    merged: dict[str, Article] = {a.id: a for a in BUILTIN}
    for id, raw in stored.items():
        try:
            merged[id] = Article.model_validate(
                {**raw, "id": id, "builtin": id in {a.id for a in BUILTIN}}
            )
        except ValueError:
            continue  # a bad stored row never breaks help
    result = []
    for article in merged.values():
        article = article.model_copy(update={"hidden": article.id in hidden})
        if include_hidden or not article.hidden:
            result.append(article)
    return sorted(result, key=lambda a: (a.hidden, not a.builtin, a.title))


def _check_page(page: str | None) -> str | None:
    if page and page not in PI_PAGES:
        raise BusinessRuleViolation("INVALID_PAGE", "Choose a page from the pi app list")
    return page


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
    return slug if len(slug) >= 2 else "article"


async def save(session: AsyncSession, id: str | None, data: ArticleInput, author: str) -> Article:
    row = await _state(session, lock=True)
    value = dict(row.value or {})
    stored = dict(value.get("articles", {}))
    known = {a.id for a in await articles(session, include_hidden=True)}
    if id is None:
        id = slugify(data.title)
        base, n = id, 2
        while id in known:
            id, n = f"{base[:56]}-{n}", n + 1
    elif id not in known:
        raise ResourceNotFound
    stored[id] = {
        **data.model_dump(),
        "page": _check_page(data.page),
        "updated_by": author[:80],
        "updated_at": _now().isoformat(),
    }
    value["articles"] = stored
    row.value = value
    await session.flush()
    return next(a for a in await articles(session, include_hidden=True) if a.id == id)


async def set_hidden(session: AsyncSession, id: str, hidden: bool) -> None:
    if id not in {a.id for a in await articles(session, include_hidden=True)}:
        raise ResourceNotFound
    row = await _state(session, lock=True)
    value = dict(row.value or {})
    hidden_ids = set(value.get("hidden", []))
    (hidden_ids.add if hidden else hidden_ids.discard)(id)
    value["hidden"] = sorted(hidden_ids)
    row.value = value
    await session.flush()


async def reset(session: AsyncSession, id: str) -> None:
    """Built-in: drop the operator's edit. Operator-added: delete it."""
    row = await _state(session, lock=True)
    value = dict(row.value or {})
    stored = dict(value.get("articles", {}))
    if id not in stored:
        raise ResourceNotFound
    stored.pop(id)
    value["articles"] = stored
    value["hidden"] = [
        h for h in value.get("hidden", []) if h != id or id in {a.id for a in BUILTIN}
    ]
    row.value = value
    await session.flush()


WORD = re.compile(r"[a-z0-9]+")
SYNONYMS = {
    "kaise": "how",
    "kesy": "how",
    "kese": "how",
    "jorna": "connect",
    "jodna": "connect",
    "connect": "connect",
    "number": "whatsapp",
    "paise": "payments",
    "paisa": "payments",
    "payment": "payments",
    "team": "team",
    "banda": "member",
    "staff": "member",
    "sikhao": "teach",
    "sikhana": "teach",
    "train": "teach",
}


def _terms(text: str) -> list[str]:
    return [SYNONYMS.get(w, w) for w in WORD.findall(text.lower()) if len(w) > 2]


def search(items: list[Article], query: str, limit: int = 3) -> list[Article]:
    """Keyword ranking: tags and title weigh more than body text."""
    terms = set(_terms(query))
    if not terms:
        return []
    scored = []
    for article in items:
        tags = set(_terms(" ".join(article.tags)))
        title = set(_terms(article.title))
        body = _terms(article.body)
        score = 3 * len(terms & tags) + 2 * len(terms & title) + sum(1 for w in body if w in terms)
        if score:
            scored.append((score, article))
    scored.sort(key=lambda pair: -pair[0])
    return [a for _, a in scored[:limit]]


def view(article: Article) -> dict[str, Any]:
    return article.model_dump(mode="json")
