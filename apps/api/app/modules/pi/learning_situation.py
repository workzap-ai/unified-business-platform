"""The situation key everything pi learns is filed under (pi Brain spec 8.2).

    situation = industry x state x category x language x person_type x turn_kind

Learned content is used only where it applies, so a dental example is never shown to a dairy
farmer. When a key has too little data pi backs off to a broader one: drop `person_type`, then
`language`, then `industry` (to its sector). Two parts of that are deliberate here:

* the reply language is never dropped: pi answers in the language the person writes (R-VOICE), so
  a Roman Urdu person is never shown an English example. Language is a hard filter, and the
  back-off drops everything else first;
* an item with no industry on it (made before industry was in the key, or general) fits everyone,
  but an item filed under an industry fits only that industry, and its sector at the last step.

Old rows with the old three-part key (state, language, turn_kind) stay readable: a missing part
means "any".
"""

import re
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import industry_packs
from app.modules.pi.models import PiConversation
from app.modules.pi.problem_models import PiProblem

KEY_PARTS = ("industry", "state", "category", "language", "person_type", "turn_kind")

OWNER_WORDS = re.compile(
    r"\b(?:owner|founder|proprietor|ceo|director|chairman|malik|maalik|sahib|partner|md)\b",
    re.IGNORECASE,
)
MANAGER_WORDS = re.compile(
    r"\b(?:manager|head|supervisor|lead|gm|coo|cfo|incharge|in-charge|admin)\b", re.IGNORECASE
)
STAFF_WORDS = re.compile(
    r"\b(?:accountant|munshi|cashier|clerk|staff|employee|assistant|operator|worker|"
    r"salesman|storekeeper|executive)\b",
    re.IGNORECASE,
)
SMALL_TEAM = 10  # people at or below which an owner counts as running a small business


def person_type_of(profile: Mapping[str, Any] | None) -> str:
    """owner_small, owner_large, owner, manager, staff, or "" when the role is not known. From the
    customer profile pi keeps (their own words about themselves), never from a name."""
    profile = profile or {}
    role = str(profile.get("role") or "")
    if OWNER_WORDS.search(role):
        size = re.search(r"\d+", str(profile.get("team_size") or ""))
        if size is None:
            return "owner"
        return "owner_small" if int(size.group()) <= SMALL_TEAM else "owner_large"
    if MANAGER_WORDS.search(role):
        return "manager"
    if STAFF_WORDS.search(role):
        return "staff"
    return ""


def sector_of(industry: str) -> str:
    """The sector code (A to M) of an industry pack, or "" when it is not a known pack."""
    pack = industry_packs.get_pack(industry or "")
    return str(((pack or {}).get("sector") or {}).get("code") or "")


def clean_industry(value: str | None) -> str:
    """The industry to file under: "" for none or "unclassified"."""
    said = (value or "").strip()
    return "" if said in ("", "unclassified") else said


def extras(
    industry: str | None, category: str | None, profile: Mapping[str, Any] | None
) -> dict[str, str]:
    """The new parts of the key that are known, ready to merge into a situation. Parts that are
    not known are left out (a missing part means "any" on old rows too)."""
    found = {
        "industry": clean_industry(industry),
        "category": (category or "").strip(),
        "person_type": person_type_of(profile),
    }
    if found["industry"] and (sector := sector_of(found["industry"])):
        found["sector"] = sector
    return {k: v for k, v in found.items() if v}


async def category_of(session: AsyncSession, conversation_id: Any, before: Any = None) -> str:
    """The category of the most recent problem noted in this chat (optionally before a time)."""
    query = (
        select(PiProblem.category)
        .where(PiProblem.conversation_id == conversation_id)
        .order_by(PiProblem.created_at.desc())
        .limit(1)
    )
    if before is not None:
        query = query.where(PiProblem.created_at <= before)
    return (await session.scalar(query)) or ""


async def industry_of(session: AsyncSession, conversation: PiConversation) -> str:
    """The primary industry of the conversation's customer, "" when unknown."""
    if not conversation.customer_id:
        return ""
    from app.modules.customers.models import Customer

    return clean_industry(
        await session.scalar(
            select(Customer.industry_primary).where(Customer.id == conversation.customer_id)
        )
    )


def backoff(
    *,
    state: str,
    language: str,
    turn_kind: str,
    industry: str = "",
    category: str = "",
    person_type: str = "",
) -> list[dict[str, str]]:
    """Broader and broader keys for one conversation (spec 8.2), most specific first. Only parts
    that are known are asked for. Language is in every level."""
    full = {
        "industry": industry,
        "state": state,
        "category": category,
        "language": language,
        "person_type": person_type,
        "turn_kind": turn_kind,
    }
    levels = [
        full,  # everything
        {**full, "person_type": ""},  # drop person_type
        {**full, "person_type": "", "category": ""},  # and the category of the problem
        {**full, "person_type": "", "category": "", "turn_kind": ""},  # and the kind of turn
        {
            "industry": industry,
            "language": language,
        },  # and the state: the industry in this language
        {"language": language},  # and the industry: anyone, in this language
    ]
    out: list[dict[str, str]] = []
    for level in levels:
        trimmed = {k: v for k, v in level.items() if v}
        if trimmed not in out:
            out.append(trimmed)
    return out


def fits(situation: Mapping[str, Any], level: Mapping[str, str]) -> bool:
    """An item's situation fits a level when every part the level asks for is the same on the item.
    A part the item does not have (an old row) is "any" and fits, except the language, which must
    be there and the same."""
    for part, wanted in level.items():
        have = situation.get(part)
        if have in (None, "") and part != "language":
            continue
        if have != wanted:
            return False
    return True


def industry_allowed(
    situation: Mapping[str, Any], industry: str, sector: str, *, sector_ok: bool
) -> bool:
    """An item filed under an industry is for that industry only (or, when `sector_ok`, for any
    industry of the same sector). An item with no industry is general and fits everyone."""
    filed = str(situation.get("industry") or "")
    if not filed or filed == industry:
        return True
    return sector_ok and bool(sector) and str(situation.get("sector") or sector_of(filed)) == sector
