"""The Business Profile (platform spec v1.4, 16.3): what pi learns about the owner's business.

A profile is a list of facts, each with its source (owner, page or photo) and whether the owner
confirmed it. Grounding rule (16.3): a fact from a page or a photo is provisional until the owner
confirms it or does not object after pi says it back; only confirmed facts count as grounded for
the idea filter (G2, OT13). Nothing personal is kept (OT15): emails, phone numbers and other
personal details found on a page are dropped, and no staff names are ever extracted.

Pure functions on a plain dict, so the profile lives on the conversation brief
(`service_brief["business_profile"]`) until it has tables of its own. No model call.
"""

import re
from typing import Any

from app.modules.pi import public_page, safety

OWNER = "owner"
PAGE = "page"
PHOTO = "photo"
SOURCES = (OWNER, PAGE, PHOTO)
KEYS = (
    "business_name",
    "what_they_do",
    "industry",
    "places",
    "since",
    "size",
    "channels",
    "website_url",
    "social_urls",
    "website",  # "none" is a fact, not a problem (16.5)
    "online_orders",
    "language",
)
_TITLE_SPLIT = re.compile(r"\s[|–—-]\s")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d")


def new_profile() -> dict[str, Any]:
    return {"facts": []}


def _clean(value: str, limit: int = 300) -> str:
    """The value without card, ID, phone and email details; empty when it was only that."""
    text = safety.redact_pii(value or "").text
    text = _PHONE.sub("", _EMAIL.sub("", text))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def add_fact(
    profile: dict[str, Any],
    key: str,
    value: str,
    source: str,
    *,
    evidence: str = "",
    url: str = "",
) -> bool:
    """Add or replace one fact. An owner's own fact is confirmed at once; a page or a photo fact is
    provisional. A fact never replaces one from a more trusted source that is confirmed. Returns
    whether the fact was stored."""
    if key not in KEYS or source not in SOURCES:
        return False
    cleaned = _clean(value)
    if not cleaned:
        return False
    facts: list[dict[str, Any]] = profile.setdefault("facts", [])
    current = next((f for f in facts if f["key"] == key), None)
    if current is not None:
        if current["confirmed"] and source != OWNER:
            return False  # a confirmed fact is not overwritten by a page
        facts.remove(current)
    facts.append(
        {
            "key": key,
            "value": cleaned,
            "source": source,
            "confirmed": source == OWNER,
            "evidence": _clean(evidence, 200),
            "url": url if source != OWNER else "",
        }
    )
    return True


def fact(profile: dict[str, Any] | None, key: str) -> dict[str, Any] | None:
    return next((f for f in (profile or {}).get("facts", []) if f["key"] == key), None)


def from_page(profile: dict[str, Any], result: public_page.PageResult) -> dict[str, Any]:
    """Provisional facts from a quick look. The page's own words only, short; no staff names and
    no contact details are read from it."""
    if not result.ok:
        return profile
    name = result.site_name or _TITLE_SPLIT.split(result.title)[0].strip()
    add_fact(profile, "business_name", name, PAGE, evidence=result.title, url=result.url)
    add_fact(
        profile, "what_they_do", result.description, PAGE, evidence=result.title, url=result.url
    )
    add_fact(profile, "website_url", result.url, OWNER)  # the owner gave it
    if result.social_links:
        add_fact(profile, "social_urls", " ".join(result.social_links), PAGE, url=result.url)
    if result.orders_online:
        add_fact(
            profile, "online_orders", "yes", PAGE, evidence="cart or order button", url=result.url
        )
    if result.lang:
        add_fact(profile, "language", result.lang, PAGE, url=result.url)
    return profile


def confirm(profile: dict[str, Any], keys: list[str] | None = None) -> dict[str, Any]:
    """The owner confirmed, or did not object after pi said the facts back."""
    for item in profile.get("facts", []):
        if keys is None or item["key"] in keys:
            item["confirmed"] = True
    return profile


def grounded(profile: dict[str, Any] | None) -> dict[str, str]:
    """The facts that count as known about this owner: the owner's own and the confirmed ones."""
    return {f["key"]: f["value"] for f in (profile or {}).get("facts", []) if f["confirmed"]}


def grounding_text(profile: dict[str, Any] | None) -> str:
    """The grounded facts as words, to be added to the owner's words for the idea filter (G2)."""
    return " ".join(f"{k} {v}" for k, v in grounded(profile).items())


def no_website(profile: dict[str, Any]) -> dict[str, Any]:
    """ "I have no website" is stored as a fact, never as a problem (16.5)."""
    add_fact(profile, "website", "none", OWNER)
    return profile


SAY_BACK = {
    "en": "From your page I understood: {what}. Tell me if anything is wrong.",
    "roman_ur": "Page se ye samajh aaya: {what}. Kuch ghalat ho to bataiye.",
}


def say_back(profile: dict[str, Any], language: str | None = None) -> str:
    """One line of what pi understood, labelled as coming from the page (never "your business is").
    Empty when the page gave nothing worth saying."""
    parts = [f["value"] for f in profile.get("facts", []) if f["source"] == PAGE]
    pieces = [
        f["value"]
        for key in ("what_they_do", "business_name")
        if (f := fact(profile, key)) is not None and f["source"] == PAGE
    ]
    if not pieces:
        return ""
    if fact(profile, "online_orders"):
        pieces.append("orders online" if language != "roman_ur" else "online order ka option")
    del parts
    what = "; ".join(dict.fromkeys(pieces))[:240]
    return SAY_BACK["roman_ur" if language == "roman_ur" else "en"].format(what=what)
