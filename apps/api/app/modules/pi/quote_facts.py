"""Platform spec v1.6 ROFFER07: the owner said yes to the offer but pi lacks facts the quote needs.

pi then asks only those facts (number of shops, locations, systems), at most two, and says why:
"taake quote sahi bane" (so the quote is accurate). The two facts go in ONE question sentence that
is the last sentence of the message, so the reply still has exactly one question (RASK01, the
non-negotiable "one question per message, and it is the last sentence").

Pure functions, no database and no model. Brain mode only: `decisions.decide` calls `ask_line` when
the facts carry a `quote_missing` list, and that list is only built for `pi_mode == "brain"`.
"""

import re
from typing import Any

# The most facts one offer message may ask for (ROFFER07).
MAX_FACTS = 2
ORDER = ("shops", "locations", "systems")

_NUMBER_WORDS = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|ek|do|teen|char|paanch|panch)"
_SHOP = r"(?:shops?|stores?|outlets?|branch(?:es)?|dukaan(?:en|ein)?|dukan(?:en|ein)?|showrooms?)"
_SHOPS_SAID = re.compile(rf"\b(?:\d+|{_NUMBER_WORDS})\s+(?:\w+\s+)?{_SHOP}\b", re.IGNORECASE)
_SHOPS_SAID_AFTER = re.compile(rf"\b{_SHOP}\s*[:=-]?\s*\d+\b", re.IGNORECASE)
_SYSTEMS_SAID = re.compile(
    r"\b(?:excel|sheets?|quickbooks?|qb|tally|pos|point of sale|register|software|erp|app|"
    r"khata|copy|notebook|paper|diary|odoo|sap|zoho|xero|shopify|system)\b",
    re.IGNORECASE,
)
_PLACES_SAID = re.compile(
    r"\b(?:in|at|near|mein|me)\s+(?:the\s+)?[A-Z][\w-]{2,}|\b(?:lahore|karachi|islamabad|"
    r"rawalpindi|faisalabad|multan|peshawar|quetta|dubai|riyadh|doha)\b",
    re.IGNORECASE,
)

_FACT_KEYS = {
    "shops": ("size",),
    "locations": ("places",),
    "systems": ("systems", "tools", "channels"),
}

ASK = {
    "en": {
        "why": "So the quote is accurate, I need one more detail.",
        "shops": "how many shops or branches you have",
        "locations": "which places they are in",
        "systems": "what you use to keep records now",
        "join": " and ",
        "form": "{why} Could you tell me {facts}?",
    },
    "roman_ur": {
        "why": "Taake quote sahi bane, mujhe aik cheez aur chahiye.",
        "shops": "kitni dukaanen ya branches hain",
        "locations": "wo kin shehron ya ilaqon mein hain",
        "systems": "abhi record kis cheez mein rakhte hain",
        "join": " aur ",
        "form": "{why} Kya aap bata dein ge ke {facts}?",
    },
    "ur": {
        "why": "تاکہ کوٹیشن درست بنے، مجھے ایک چیز اور چاہیے۔",
        "shops": "آپ کی کتنی دکانیں یا برانچیں ہیں",
        "locations": "وہ کن شہروں یا علاقوں میں ہیں",
        "systems": "ابھی ریکارڈ کس چیز میں رکھتے ہیں",
        "join": " اور ",
        "form": "{why} کیا آپ بتا دیں گے کہ {facts}؟",
    },
    "ar": {
        "why": "ليكون عرض السعر دقيقاً، أحتاج إلى تفصيل واحد.",
        "shops": "كم عدد المتاجر أو الفروع لديكم",
        "locations": "في أي أماكن تقع",
        "systems": "ماذا تستخدمون الآن لحفظ السجلات",
        "join": " و",
        "form": "{why} هل يمكنكم إخباري {facts}؟",
    },
}


def _language(language: str | None) -> str:
    key = (language or "en").split("-")[0]
    if key == "hi":
        key = "ur"
    if key == "ur" and language in ("roman_ur", "ur-Latn"):
        key = "roman_ur"
    return key if key in ASK else "en"


def missing(context: dict[str, Any]) -> list[str]:
    """The quote facts pi does not have yet, in `ORDER`, at most `MAX_FACTS`. A fact counts as
    known when the stored profile holds it, a noted problem says where it happens, or the owner
    said it in the chat. Never raises."""
    try:
        profile = (context.get("brief") or {}).get("business_profile") or {}
        stored = {
            str(f.get("key")): str(f.get("value") or "")
            for f in profile.get("facts") or []
            if isinstance(f, dict)
        }
        owner = " ".join(
            [
                *(
                    str(h.get("text") or "")
                    for h in context.get("history") or []
                    if h.get("role") == "customer"
                ),
                *(str(t) for t in context.get("burst_texts") or []),
                str(context.get("latest_customer_message") or ""),
            ]
        )
        noted = context.get("noted_problems") or []
        known = {
            "shops": any(stored.get(k) for k in _FACT_KEYS["shops"])
            or bool(_SHOPS_SAID.search(owner) or _SHOPS_SAID_AFTER.search(owner)),
            "locations": any(stored.get(k) for k in _FACT_KEYS["locations"])
            or any(p.get("where") for p in noted)
            or bool(_PLACES_SAID.search(owner)),
            "systems": any(stored.get(k) for k in _FACT_KEYS["systems"])
            or bool(_SYSTEMS_SAID.search(owner)),
        }
        return [k for k in ORDER if not known[k]][:MAX_FACTS]
    except Exception:  # noqa: BLE001 - a missing detail must never stop the quote
        return []


def ask_line(keys: list[str], language: str | None) -> str:
    """The one message that asks for `keys` (at most two) and says why. Exactly one question, and
    it is the last sentence."""
    table = ASK[_language(language)]
    chosen = [k for k in ORDER if k in keys][:MAX_FACTS]
    facts = table["join"].join(table[k] for k in chosen)
    return table["form"].format(why=table["why"], facts=facts)


def question_count(reply: str) -> int:
    """How many question marks end a sentence in `reply` (Latin and Arabic-script marks)."""
    return len(re.findall(r"[?؟]", reply or ""))


def too_many_questions(reply: str) -> bool:
    """ROFFER07: a message asking for the quote's facts holds at most two questions."""
    return question_count(reply) > MAX_FACTS
