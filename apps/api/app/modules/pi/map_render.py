"""Drawing the problem map as pictures (pi Brain spec, Part 4.6 and 4.7).

Pure rendering: a map dict goes in, PNG bytes, a caption, alt text and a text fallback come out.
Nothing here reads a database or sends a message.

    map = {
        "version": 3,
        "nodes": [{"id", "label", "facts": [..], "category", "is_new", "status"}],
        "links": [{"from", "to", "type", "label", "evidence"}],  # owner_said|pi_inferred|confirmed
        "clusters": [{"id", "title", "node_ids": [..]}],
    }

What the picture follows (spec 4.6): 1080 wide, portrait, PNG well under 5 MB; at most nine problems
per image (more: one overview with a bubble per cluster, then one detail image per cluster); no
text under 24 px; a colour bar per category group (five hues at most); cool light-grey background
and a dark header; solid dark arrows for what the owner said or confirmed, dashed grey for pi's
guess; a "Naya" tag on new problems; a dashed outline and a short title round each cluster; a
legend and a footer saying only the owner's numbers are used and no names appear.

Layout is deterministic: no randomness, ties broken by the order the nodes arrive in, and a
`previous` slot map keeps old problems where they were when the map grows. The same map always
gives the same bytes, so a picture can be cached by `map_hash`.

Scripts. Latin text (English, Roman Urdu) uses Pillow's bundled font. Urdu, Arabic and Persian
(Pashto and Sindhi borrow the Urdu words) are drawn right to left with Noto Naskh Arabic (SIL OFL,
`fonts/`): each line is shaped with `arabic_reshaper` and put in visual order with `python-bidi`
(Pillow here has no raqm), and the layout is mirrored (first card on the right, text right-aligned,
arrows read leftwards). Naskh has no Latin letters, so Latin runs ("Workzap", Roman words) are drawn
with the Latin font. If the font file or the two packages are missing at run time, or a word needs a
glyph the font lacks, the picture is skipped and the right-to-left text fallback comes back with the
reason; never a badly shaped picture.

Safety: every drawn word passes the project's redactor, long digit runs, e-mail addresses and
links are removed, and when the owner's messages are supplied a number the owner never said is not
drawn (`numbers_supported` checks the same thing for a whole map).
"""

import hashlib
import io
import json
import re
import threading
import zlib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.modules.pi import safety

WIDTH = 1080
MIN_HEIGHT = 640
MAX_HEIGHT = 1920
MAX_NODES = 9
MAX_BUBBLES = 12
MAX_HUES = 5
MIN_TEXT_PX = 24
MAX_PNG_BYTES = 5 * 1024 * 1024
MAX_LABEL_WORDS = 9
MAX_LINK_WORDS = 3
MAX_FACT_LINES = 3

DRAWABLE_LANGUAGES = ("en", "roman_ur", "ur", "ar", "fa", "fr", "es")
RTL_LANGUAGES = ("ur", "ar", "fa", "ps", "sd")
FONT_DIR = Path(__file__).parent / "fonts"
NASKH_REGULAR = FONT_DIR / "NotoNaskhArabic-Regular.ttf"
NASKH_BOLD = FONT_DIR / "NotoNaskhArabic-Bold.ttf"

# Colours (RGB). Text pairs are listed in TEXT_PAIRS and checked by the tests (WCAG, 4.5 to 1).
BG = (238, 242, 246)
HEADER_BG = (31, 41, 51)
HEADER_INK = (255, 255, 255)
HEADER_SUB = (203, 213, 225)
CARD = (255, 255, 255)
INK = (31, 41, 51)
MUTED = (75, 85, 99)
ARROW_SOLID = (31, 41, 51)
ARROW_DASH = (96, 104, 112)
OUTLINE = (96, 104, 112)
TAG_BG = (251, 191, 36)
TAG_INK = (31, 41, 51)
RESOLVED_BAR = (156, 163, 175)
HUES = (
    (13, 148, 136),
    (217, 119, 6),
    (220, 38, 38),
    (37, 99, 235),
    (101, 163, 13),
)
TEXT_PAIRS = (
    (INK, CARD),
    (MUTED, CARD),
    (INK, BG),
    (MUTED, BG),
    (HEADER_INK, HEADER_BG),
    (HEADER_SUB, HEADER_BG),
    (TAG_INK, TAG_BG),
)

TEXT: dict[str, dict[str, Any]] = {
    "en": {
        "header": "Your business map",
        "version": "Version",
        "summary": "{version} {v} · {pc} · {lc}",
        "problem": "problem",
        "problems": "problems",
        "link": "link",
        "links": "links",
        "new": "New",
        "stale": "From last time",
        "legend_owner": "You said it",
        "legend_guess": "My guess",
        "legend_new": "added",
        "foot": "Your numbers only. No names.",
        "no_links": "No links yet",
        "overview": "Overview",
        "cluster": "One root: {title}",
        "others": "Other problems",
        "more": "More below",
        "caption": "Here is what I have so far: {pc}, {lc}. Is this right? Tell me what to change.",
        "caption_overview": "{version} {v}, overview: {k} groups.",
        "caption_detail": "{version} {v}, {title}: {pc}.",
        "alt_node": "Problem: {label}",
        "alt_guess": "my guess, please confirm",
        "alt_link": "Link: {a} to {b} ({label}; {kind})",
        "alt_owner": "you said it",
        "types": {
            "causes": "leads to",
            "worsens": "worsens",
            "competes": "competes",
            "same_root": "same root",
            "blocks": "blocks",
            "symptom_of": "symptom of",
        },
        "guess_note": "(my guess)",
    },
    "roman_ur": {
        "header": "Aap ke karobar ka naqsha",
        "version": "Version",
        "summary": "{version} {v} · {pc} · {lc}",
        "problem": "masla",
        "problems": "masle",
        "link": "jorr",
        "links": "jorr",
        "new": "Naya",
        "stale": "Pichli baar ka",
        "legend_owner": "Aap ne bataya",
        "legend_guess": "Hamara andaza",
        "legend_new": "naya",
        "foot": "Sirf aap ke bataye hue number. Koi naam ya zaati tafseel nahi.",
        "no_links": "Abhi koi jorr nahi",
        "overview": "Mukhtasar naqsha",
        "cluster": "Ek hi jar: {title}",
        "others": "Baqi masle",
        "more": "Aage dekhein",
        "caption": "{version} {v}: {pc}, {lc}.",
        "caption_overview": "{version} {v}, mukhtasar: {k} hisse.",
        "caption_detail": "{version} {v}, {title}: {pc}.",
        "alt_node": "Masla: {label}",
        "alt_guess": "hamara andaza, aap tasdeeq karein",
        "alt_link": "Jorr: {a} se {b} ({label}; {kind})",
        "alt_owner": "aap ne bataya",
        "types": {
            "causes": "asar",
            "worsens": "bigarta",
            "competes": "takrao",
            "same_root": "ek jar",
            "blocks": "rukawat",
            "symptom_of": "nishani",
        },
        "guess_note": "(hamara andaza)",
    },
    # Urdu script (Pashto and Sindhi readers get these words too). Gender neutral: "aap", no verbs
    # that change with the speaker.
    "ur": {
        "header": "آپ کے کاروبار کا نقشہ",
        "version": "ورژن",
        "summary": "{version} {v} · {pc} · {lc}",
        "problem": "مسئلہ",
        "problems": "مسئلے",
        "link": "جوڑ",
        "links": "جوڑ",
        "new": "نیا",
        "stale": "پچھلی بار کا",
        "legend_owner": "آپ نے بتایا",
        "legend_guess": "ہمارا اندازہ",
        "legend_new": "شامل ہوا",
        "foot": "صرف آپ کے بتائے ہوئے نمبر۔ کوئی نام یا ذاتی تفصیل نہیں۔",
        "no_links": "ابھی کوئی جوڑ نہیں",
        "overview": "مختصر نقشہ",
        "cluster": "ایک ہی جڑ: {title}",
        "others": "باقی مسئلے",
        "more": "آگے دیکھیں",
        "caption": "{version} {v}: {pc}، {lc}۔",
        "caption_overview": "{version} {v}، مختصر نقشہ: {k} حصے۔",
        "caption_detail": "{version} {v}، {title}: {pc}۔",
        "alt_node": "مسئلہ: {label}",
        "alt_guess": "ہمارا اندازہ، براہِ کرم تصدیق کریں",
        "alt_link": "جوڑ: {a} سے {b} ({label}؛ {kind})",
        "alt_owner": "آپ نے بتایا",
        "types": {
            "causes": "اثر",
            "worsens": "بگاڑ",
            "competes": "ٹکراؤ",
            "same_root": "ایک جڑ",
            "blocks": "رکاوٹ",
            "symptom_of": "نشانی",
        },
        "guess_note": "(ہمارا اندازہ)",
    },
    "ar": {
        "header": "خريطة نشاطك التجاري",
        "version": "الإصدار",
        "summary": "{version} {v} · {pc} · {lc}",
        "problem": "مشكلة",
        "problems": "مشكلات",
        "n_problem": "المشكلات: {n}",
        "n_link": "الروابط: {n}",
        "link": "رابط",
        "links": "روابط",
        "new": "جديد",
        "stale": "من المرة السابقة",
        "legend_owner": "من كلامك",
        "legend_guess": "تقديرنا",
        "legend_new": "تمت إضافته",
        "foot": "الأرقام المستخدمة هي التي ذكرتها فقط. بلا أسماء أو بيانات شخصية.",
        "no_links": "لا روابط بعد",
        "overview": "نظرة عامة",
        "cluster": "جذر واحد: {title}",
        "others": "مشكلات أخرى",
        "more": "المزيد أدناه",
        "caption": "{version} {v}: {pc}، {lc}.",
        "caption_overview": "{version} {v}، نظرة عامة: عدد المجموعات {k}.",
        "caption_detail": "{version} {v}، {title}: {pc}.",
        "alt_node": "مشكلة: {label}",
        "alt_guess": "تقديرنا، يرجى التأكيد",
        "alt_link": "رابط: من {a} إلى {b} ({label}؛ {kind})",
        "alt_owner": "من كلامك",
        "types": {
            "causes": "يسبب",
            "worsens": "يفاقم",
            "competes": "يتنافس",
            "same_root": "جذر واحد",
            "blocks": "يعيق",
            "symptom_of": "من أعراض",
        },
        "guess_note": "(تقديرنا)",
    },
    "fa": {
        "header": "نقشه کسب‌وکار شما",
        "version": "نسخه",
        "summary": "{version} {v} · {pc} · {lc}",
        "problem": "مشکل",
        "problems": "مشکل",
        "link": "پیوند",
        "links": "پیوند",
        "new": "جدید",
        "stale": "از دفعه قبل",
        "legend_owner": "گفته شما",
        "legend_guess": "حدس ما",
        "legend_new": "افزوده شد",
        "foot": "فقط عددهایی که شما گفتید استفاده شده است. بدون نام یا مشخصات شخصی.",
        "no_links": "هنوز پیوندی نیست",
        "overview": "نمای کلی",
        "cluster": "یک ریشه: {title}",
        "others": "مشکل‌های دیگر",
        "more": "ادامه در پایین",
        "caption": "{version} {v}: {pc}، {lc}.",
        "caption_overview": "{version} {v}، نمای کلی: {k} گروه.",
        "caption_detail": "{version} {v}، {title}: {pc}.",
        "alt_node": "مشکل: {label}",
        "alt_guess": "حدس ما، لطفاً تأیید کنید",
        "alt_link": "پیوند: {a} به {b} ({label}؛ {kind})",
        "alt_owner": "گفته شما",
        "types": {
            "causes": "اثر",
            "worsens": "تشدید",
            "competes": "رقابت",
            "same_root": "یک ریشه",
            "blocks": "مانع",
            "symptom_of": "نشانه",
        },
        "guess_note": "(حدس ما)",
    },
    "fr": {
        "header": "La carte de votre activité",
        "version": "Version",
        "summary": "{version} {v} · {pc} · {lc}",
        "problem": "problème",
        "problems": "problèmes",
        "link": "lien",
        "links": "liens",
        "new": "Nouveau",
        "stale": "De la dernière fois",
        "legend_owner": "Vous l'avez dit",
        "legend_guess": "Mon hypothèse",
        "legend_new": "ajouté",
        "foot": "Seuls vos chiffres sont utilisés. Ni noms ni données personnelles.",
        "no_links": "Pas encore de lien",
        "overview": "Vue d'ensemble",
        "cluster": "Une racine : {title}",
        "others": "Autres problèmes",
        "more": "Suite ci-dessous",
        "caption": "{version} {v} : {pc}, {lc}.",
        "caption_overview": "{version} {v}, vue d'ensemble : {k} groupes.",
        "caption_detail": "{version} {v}, {title} : {pc}.",
        "alt_node": "Problème : {label}",
        "alt_guess": "mon hypothèse, merci de confirmer",
        "alt_link": "Lien : {a} vers {b} ({label} ; {kind})",
        "alt_owner": "vous l'avez dit",
        "types": {
            "causes": "mène à",
            "worsens": "aggrave",
            "competes": "est en concurrence",
            "same_root": "même racine",
            "blocks": "bloque",
            "symptom_of": "symptôme de",
        },
        "guess_note": "(mon hypothèse)",
    },
    "es": {
        "header": "El mapa de su negocio",
        "version": "Versión",
        "summary": "{version} {v} · {pc} · {lc}",
        "problem": "problema",
        "problems": "problemas",
        "link": "vínculo",
        "links": "vínculos",
        "new": "Nuevo",
        "stale": "De la vez anterior",
        "legend_owner": "Usted lo dijo",
        "legend_guess": "Mi suposición",
        "legend_new": "añadido",
        "foot": "Solo se usan los números que usted dio. Sin nombres ni datos personales.",
        "no_links": "Aún sin vínculos",
        "overview": "Vista general",
        "cluster": "Una raíz: {title}",
        "others": "Otros problemas",
        "more": "Más abajo",
        "caption": "{version} {v}: {pc}, {lc}.",
        "caption_overview": "{version} {v}, vista general: {k} grupos.",
        "caption_detail": "{version} {v}, {title}: {pc}.",
        "alt_node": "Problema: {label}",
        "alt_guess": "mi suposición, por favor confirme",
        "alt_link": "Vínculo: {a} a {b} ({label}; {kind})",
        "alt_owner": "usted lo dijo",
        "types": {
            "causes": "lleva a",
            "worsens": "empeora",
            "competes": "compite",
            "same_root": "misma raíz",
            "blocks": "bloquea",
            "symptom_of": "síntoma de",
        },
        "guess_note": "(mi suposición)",
    },
}

# Names for the colour legend in right-to-left maps (the category keys come from taxonomy.py).
CATEGORY_NAMES: dict[str, dict[str, str]] = {
    "fr": {
        "stock_inventory": "Stock",
        "sales_revenue": "Ventes",
        "cash_collections": "Trésorerie et encaissements",
        "margin_cost": "Marge et coûts",
        "customers_retention": "Clients",
        "marketing_leads": "Marketing",
        "orders_fulfilment": "Commandes et livraison",
        "suppliers_purchasing": "Fournisseurs et achats",
        "people_staff": "Équipe",
        "operations_process": "Opérations",
        "reporting_visibility": "Suivi et rapports",
        "tech_systems": "Outils",
        "quality_complaints": "Qualité",
        "compliance_admin": "Administratif et légal",
        "communication_coordination": "Coordination",
        "loss_security": "Pertes et sécurité",
        "planning_growth": "Planification et croissance",
        "customer_experience_digital": "Présence en ligne",
        "other": "Autre",
    },
    "es": {
        "stock_inventory": "Inventario",
        "sales_revenue": "Ventas",
        "cash_collections": "Caja y cobros",
        "margin_cost": "Margen y costos",
        "customers_retention": "Clientes",
        "marketing_leads": "Marketing",
        "orders_fulfilment": "Pedidos y entregas",
        "suppliers_purchasing": "Proveedores y compras",
        "people_staff": "Personal",
        "operations_process": "Operaciones",
        "reporting_visibility": "Informes",
        "tech_systems": "Herramientas",
        "quality_complaints": "Calidad",
        "compliance_admin": "Administración y legal",
        "communication_coordination": "Coordinación",
        "loss_security": "Pérdidas y seguridad",
        "planning_growth": "Planificación y crecimiento",
        "customer_experience_digital": "Presencia en línea",
        "other": "Otros",
    },
    "fa": {
        "stock_inventory": "موجودی کالا",
        "sales_revenue": "فروش",
        "cash_collections": "پول و دریافتی",
        "margin_cost": "سود و هزینه",
        "customers_retention": "مشتریان",
        "marketing_leads": "بازاریابی",
        "orders_fulfilment": "سفارش و تحویل",
        "suppliers_purchasing": "تأمین‌کنندگان و خرید",
        "people_staff": "کارکنان",
        "operations_process": "عملیات",
        "reporting_visibility": "گزارش‌ها",
        "tech_systems": "سامانه‌ها",
        "quality_complaints": "کیفیت",
        "compliance_admin": "امور اداری و قانونی",
        "communication_coordination": "هماهنگی",
        "loss_security": "ضرر و امنیت",
        "planning_growth": "برنامه‌ریزی و رشد",
        "customer_experience_digital": "حضور آنلاین",
        "other": "سایر",
    },
}


def category_name(category: str, lang: str) -> str:
    """The legend name of a category: localised for right-to-left maps, else the key as words."""
    if lang in ("ur", "ar"):
        from app.modules.pi import taxonomy

        found = taxonomy.BY_KEY.get(category)
        if found:
            return str(getattr(found, lang))
    elif lang in CATEGORY_NAMES and category in CATEGORY_NAMES[lang]:
        return CATEGORY_NAMES[lang][category]
    return category.replace("_", " ")


def count_phrase(words: dict[str, Any], kind: str, n: int) -> str:
    """ "3 problems" (or the language's own counted form, e.g. Arabic "المشكلات: 3")."""
    template = words.get(f"n_{kind}")
    if template:
        return str(template).format(n=n)
    return f"{n} {words[kind + 's'] if n != 1 else words[kind]}"


def counts(words: dict[str, Any], version: int, n: int, links: int) -> dict[str, Any]:
    """The fields every summary or caption template may use."""
    return {
        "version": words["version"],
        "v": version,
        "n": n,
        "l": links,
        "pc": count_phrase(words, "problem", n),
        "lc": count_phrase(words, "link", links)
        if links or "no_links" not in words
        else words["no_links"],
    }


def _words(language: str | None) -> dict[str, Any]:
    return TEXT.get(language or "en", TEXT["en"])


def is_rtl(language: str | None) -> bool:
    return (language or "").split("-")[0].lower() in RTL_LANGUAGES


def _lang(language: str | None) -> str:
    base = (language or "en").split("-")[0].lower()
    if base in DRAWABLE_LANGUAGES:
        return base
    return "ur" if base in RTL_LANGUAGES else "en"


def share_language(language: str | None) -> str:
    """The language the whole map message uses, so the picture and the line that comes with it
    never mix scripts: a language the picture cannot be drawn in (Hindi has no bundled font yet)
    gets English for both."""
    return _lang(language)


# --- numbers and personal data ------------------------------------------------------------------

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_LONG_DIGITS = re.compile(r"\+?\d(?:[ -]?\d){6,}")


def _normal_number(token: str) -> str:
    whole, _, frac = token.replace(",", "").partition(".")
    whole = whole.lstrip("0") or "0"
    frac = frac.rstrip("0")
    return f"{whole}.{frac}" if frac else whole


def numbers_in(text: str) -> list[str]:
    """Every number in the text, normalised (commas out, Eastern digits turned into 0-9)."""
    return [_normal_number(m) for m in _NUMBER.findall((text or "").translate(_DIGITS))]


def _node_texts(node: dict[str, Any]) -> list[str]:
    out = [str(node.get("label") or "")]
    out += [str(f) for f in (node.get("facts") or [])]
    return out


def drawn_texts(map_: dict[str, Any]) -> list[str]:
    """Every piece of the map's own words that is drawn on some image."""
    out: list[str] = []
    for node in map_.get("nodes") or []:
        out += _node_texts(node)
    for link in map_.get("links") or []:
        out.append(str(link.get("label") or ""))
    for cluster in map_.get("clusters") or []:
        out.append(str(cluster.get("title") or ""))
    return out


def numbers_supported(map_: dict[str, Any], messages: list[str]) -> tuple[bool, list[str]]:
    """True when every number the map draws is a number the owner wrote in their messages.

    Returns (ok, the numbers that no message supports). The header counts (version, problems,
    links) are the map's own bookkeeping and are not part of this check.
    """
    said: set[str] = set()
    for message in messages:
        said.update(numbers_in(message))
    missing: list[str] = []
    for text in drawn_texts(map_):
        for number in numbers_in(text):
            if number not in said and number not in missing:
                missing.append(number)
    return not missing, missing


def _clean(text: Any, said: set[str] | None, limit: int | None = None) -> str:
    """The text as it may be drawn: personal data out, numbers the owner never said out."""
    value = str(text or "")
    value = safety.redact_pii(value).text
    value = safety.FILLER_WORDS.sub("", value)
    for pattern in (_EMAIL, _URL, _LONG_DIGITS):
        value = pattern.sub("", value)
    if said is not None:

        def keep(m: re.Match[str]) -> str:
            ok = _normal_number(m.group(0).translate(_DIGITS)) in said
            return m.group(0) if ok else ""

        value = _NUMBER.sub(keep, value)
    value = re.sub(r"\s+", " ", value).strip(" ,;:-")
    if limit:
        parts = value.split()
        if len(parts) > limit:
            value = " ".join(parts[:limit])
    return value


# --- the map as data ----------------------------------------------------------------------------

_DIRECTED = {"causes", "worsens", "blocks", "symptom_of"}
_PLAIN = {"competes", "same_root"}
_SOLID = {"owner_said", "confirmed"}


@dataclass
class Node:
    id: str
    label: str
    facts: list[str]
    category: str
    is_new: bool
    resolved: bool
    stale: bool = False  # untouched for 90 days: "pichli baar ka" until the owner confirms
    parked: bool = False


@dataclass
class Link:
    a: str
    b: str
    type: str
    label: str
    solid: bool


@dataclass
class Cluster:
    id: str
    title: str
    node_ids: list[str]


@dataclass
class Prepared:
    version: int
    nodes: list[Node]
    links: list[Link]
    clusters: list[Cluster]
    dropped: list[str] = field(default_factory=list)


def _prepare(map_: dict[str, Any], said: set[str] | None) -> Prepared:
    nodes: list[Node] = []
    seen: set[str] = set()
    dropped: list[str] = []
    for raw in map_.get("nodes") or []:
        nid = str(raw.get("id"))
        if nid in seen:
            continue
        seen.add(nid)
        facts: list[str] = []
        for fact in raw.get("facts") or []:
            if said is not None and any(n not in said for n in numbers_in(str(fact))):
                dropped.append(str(fact))
                continue
            text = _clean(fact, said)
            if text:
                facts.append(text)
        nodes.append(
            Node(
                id=nid,
                label=_clean(raw.get("label"), said, MAX_LABEL_WORDS) or "?",
                facts=facts,
                category=str(raw.get("category") or "other"),
                is_new=bool(raw.get("is_new")),
                resolved=str(raw.get("status") or "") == "resolved",
                stale=bool(raw.get("stale")),
                parked=str(raw.get("status") or "") == "parked",
            )
        )
    links: list[Link] = []
    for raw in map_.get("links") or []:
        a, b = str(raw.get("from")), str(raw.get("to"))
        if a not in seen or b not in seen or a == b:
            continue
        links.append(
            Link(
                a=a,
                b=b,
                type=str(raw.get("type") or "causes"),
                label=_clean(raw.get("label"), said, MAX_LINK_WORDS),
                solid=str(raw.get("evidence") or "pi_inferred") in _SOLID,
            )
        )
    clusters: list[Cluster] = []
    for raw in map_.get("clusters") or []:
        ids = [str(i) for i in raw.get("node_ids") or [] if str(i) in seen]
        if ids:
            clusters.append(
                Cluster(str(raw.get("id") or len(clusters)), _clean(raw.get("title"), said, 8), ids)
            )
    return Prepared(int(map_.get("version") or 1), nodes, links, clusters, dropped)


def map_hash(map_: dict[str, Any], language: str | None = None) -> str:
    """Cache key for a picture: same map and language, same hash."""
    body = json.dumps([map_, language or "en"], sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode()).hexdigest()


# --- layout -------------------------------------------------------------------------------------

CARD_W = 440
CARD_H = 212
COL_GAP = 104
MARGIN = 48
GAP_Y = 80
HEADER_H = 150
PAD_TOP = 30
OUTLINE_PAD = 14
OUTLINE_TITLE = 44
COLS = 2
LABEL_PX = 30
FACT_PX = MIN_TEXT_PX
COMPACT_MAX_NODES = (
    4  # up to this many problems: one wide column, so the picture is not mostly empty
)
_GEO_LOCK = threading.Lock()

Slot = tuple[int, int]  # (row, column)


def _ranks(nodes: list[Node], links: list[Link]) -> dict[str, int]:
    """How far down the chain each problem sits: roots first. Cycle-safe, deterministic."""
    rank = {n.id: 0 for n in nodes}
    edges = []
    for link in links:
        if link.type == "symptom_of":
            edges.append((link.b, link.a))  # the cause comes first
        elif link.type in _DIRECTED:
            edges.append((link.a, link.b))
    for _ in range(len(nodes)):
        changed = False
        for a, b in edges:
            if rank[b] < rank[a] + 1 and rank[a] + 1 < len(nodes):
                rank[b] = rank[a] + 1
                changed = True
        if not changed:
            break
    return rank


def layout(
    nodes: list[Node],
    links: list[Link],
    clusters: list[Cluster],
    previous: dict[str, Slot] | None = None,
    cluster_rows: bool = False,
) -> dict[str, Slot]:
    """A slot (row, column) for every node. Old nodes in `previous` keep theirs where free."""
    rank = _ranks(nodes, links)
    cluster_of: dict[str, int] = {}
    for index, cluster in enumerate(clusters):
        for nid in cluster.node_ids:
            cluster_of.setdefault(nid, index)
    order = {n.id: i for i, n in enumerate(nodes)}
    ranked = sorted(
        nodes,
        key=lambda n: (cluster_of.get(n.id, len(clusters)), rank[n.id], order[n.id]),
    )
    slots: dict[str, Slot] = {}
    taken: set[Slot] = set()
    for node in ranked:
        slot = (previous or {}).get(node.id)
        if slot and slot[1] < COLS and slot not in taken:
            slots[node.id] = slot
            taken.add(slot)
    row, col, last_cluster = 0, 0, None
    for node in ranked:
        if node.id in slots:
            continue
        group = cluster_of.get(node.id, len(clusters))
        if cluster_rows and last_cluster is not None and group != last_cluster and col:
            row, col = row + 1, 0
        last_cluster = group
        while (row, col) in taken:
            col += 1
            if col >= COLS:
                row, col = row + 1, 0
        slots[node.id] = (row, col)
        taken.add((row, col))
    return slots


def _geometry(slots: dict[str, Slot], rtl: bool = False) -> tuple[dict[str, tuple[int, int]], int]:
    """Top-left pixel of every card (empty rows squeezed out) and the height the cards use.

    Right to left: column 0 is the right-hand column, so the first problem sits on the right.
    """
    rows = sorted({s[0] for s in slots.values()})
    row_index = {r: i for i, r in enumerate(rows)}
    alone = {r: sum(1 for s in slots.values() if s[0] == r) == 1 for r in rows}
    pos: dict[str, tuple[int, int]] = {}
    for nid, (row, col) in slots.items():
        x = MARGIN + col * (CARD_W + COL_GAP)
        if rtl:
            x = WIDTH - x - CARD_W
        if alone[row]:
            x = (WIDTH - CARD_W) // 2
        pos[nid] = (x, HEADER_H + PAD_TOP + OUTLINE_TITLE + row_index[row] * (CARD_H + GAP_Y))
    used = len(rows) * CARD_H + max(0, len(rows) - 1) * GAP_Y
    return pos, used


# --- drawing primitives -------------------------------------------------------------------------


NASKH_SCALE = 1.1  # Naskh looks smaller than the Latin font at the same size
_NEUTRAL = " ​‌‍‎‏⁦⁧⁨⁩‪‫‬‭‮"
_LATIN_PUNCT = "–—‘’“”…·"


def _font(size: int, bold: bool = False, naskh: bool = False) -> Any:
    size = max(size, MIN_TEXT_PX)
    if naskh:
        return _naskh_font(round(size * NASKH_SCALE), bold)
    return ImageFont.load_default(size=size)


@lru_cache(maxsize=64)
def _naskh_font(size: int, bold: bool) -> Any:
    return ImageFont.truetype(str(NASKH_BOLD if bold else NASKH_REGULAR), size)


@lru_cache(maxsize=1)
def _load_rtl() -> tuple[Any, Any]:
    """The shaping tools and both Naskh fonts; ImportError or OSError when something is missing."""
    import arabic_reshaper  # type: ignore[import-untyped]
    from bidi.algorithm import get_display  # type: ignore[import-untyped]

    _naskh_font(MIN_TEXT_PX, False)
    _naskh_font(MIN_TEXT_PX, True)
    return arabic_reshaper.reshape, get_display


@lru_cache(maxsize=4096)
def shape_rtl(text: str) -> str:
    """The line in visual (left to right) order with joined letter forms, ready to draw."""
    reshape, display = _load_rtl()
    return str(display(reshape(text), base_dir="R"))


@lru_cache(maxsize=1)
def _naskh_missing() -> tuple[Any, float]:
    font = _naskh_font(MIN_TEXT_PX, False)
    return font.getbbox("￿"), float(font.getlength("￿"))


@lru_cache(maxsize=4096)
def _naskh_has(char: str) -> bool:
    font = _naskh_font(MIN_TEXT_PX, False)
    return (font.getbbox(char), float(font.getlength(char))) != _naskh_missing()


def _latin_ok(char: str) -> bool:
    return ord(char) < 0x250 or char in _LATIN_PUNCT


def _uses_latin_font(char: str) -> bool:
    """Naskh lacks Latin letters, brackets, hyphen, dot and ellipsis: those use the Latin font."""
    if char in _NEUTRAL:
        return False
    if char.isalpha() and ord(char) < 0x250:
        return True
    return not _naskh_has(char)


def _runs(visual: str) -> list[tuple[str, bool]]:
    """Split a shaped line into (text, is_latin) runs; spaces stay with the run before them."""
    runs: list[tuple[str, bool]] = []
    for char in visual:
        latin = _uses_latin_font(char)
        if char in _NEUTRAL and runs:
            latin = runs[-1][1]
        if runs and runs[-1][1] == latin:
            runs[-1] = (runs[-1][0] + char, latin)
        else:
            runs.append((char, latin))
    return runs


def rtl_drawable(text: str) -> bool:
    """True when every character of the (shaped) text has a glyph in Naskh or the Latin font."""
    for char in shape_rtl(text):
        if char in _NEUTRAL or _naskh_has(char):
            continue
        if not _latin_ok(char):
            return False
    return True


class Canvas:
    """A PNG being drawn. Records every text that does not fit its box or leaves the image.

    With `rtl` set, every text is shaped and ordered for right-to-left script and drawn with the
    Naskh font (Latin runs with the Latin font); the callers mirror the layout.
    """

    def __init__(self, height: int, rtl: bool = False) -> None:
        self.height = max(MIN_HEIGHT, min(height, MAX_HEIGHT))
        self.rtl = rtl
        self.image = Image.new("RGB", (WIDTH, self.height), BG)
        self.draw = ImageDraw.Draw(self.image)
        self.overflow: list[str] = []
        self.smallest = 10_000

    def width_of(self, text: str, size: int, bold: bool = False) -> float:
        if not self.rtl:
            return float(self.draw.textlength(text, font=_font(size)))
        return sum(
            float(self.draw.textlength(run, font=_font(size, bold, not latin)))
            for run, latin in _runs(shape_rtl(text))
        )

    def wrap(
        self, text: str, size: int, width: int, max_lines: int, bold: bool = False
    ) -> list[str]:
        """Lines that fit `width`; the last ends with an ellipsis when the text is cut."""

        def wide(value: str) -> float:
            return self.width_of(value, size, bold)

        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            while wide(word) > width:  # one very long word
                cut = len(word)
                while cut > 1 and wide(word[:cut]) > width:
                    cut -= 1
                if current:
                    lines.append(current)
                    current = ""
                lines.append(word[:cut])
                word = word[cut:]
            trial = f"{current} {word}".strip()
            if current and wide(trial) > width:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            last = lines[-1]
            while last and wide(last + "…") > width:
                last = last[:-1]
            lines[-1] = last.rstrip() + "…"
        return lines

    def text(
        self,
        xy: tuple[float, float],
        text: str,
        size: int,
        fill: tuple[int, int, int],
        width: int | None = None,
        anchor: str = "la",
        bold: bool = False,
    ) -> None:
        self.smallest = min(self.smallest, max(size, MIN_TEXT_PX))
        if self.rtl:
            self._text_rtl(xy, text, size, fill, width, anchor, bold)
            return
        font = _font(size)
        box = self.draw.textbbox(xy, text, font=font, anchor=anchor)
        if box[0] < 0 or box[2] > WIDTH or box[3] > self.height or box[1] < 0:
            self.overflow.append(text)
        elif width is not None and (box[2] - box[0]) > width + 0.5:
            self.overflow.append(text)
        self.draw.text(xy, text, fill=fill, font=font, anchor=anchor)

    def _text_rtl(
        self,
        xy: tuple[float, float],
        text: str,
        size: int,
        fill: tuple[int, int, int],
        width: int | None,
        anchor: str,
        bold: bool,
    ) -> None:
        """Draw run by run on one baseline; `xy` is the top left or top right of the line."""
        runs = _runs(shape_rtl(text))
        fonts = [_font(size, bold, not latin) for _, latin in runs]
        total = sum(
            float(self.draw.textlength(run, font=f))
            for (run, _), f in zip(runs, fonts, strict=True)
        )
        x = xy[0] if anchor.startswith("l") else xy[0] - total
        baseline = xy[1] + _font(size).getmetrics()[0]
        x0, top, x1, bottom = x, 10_000.0, x, -10_000.0
        for (run, _), font in zip(runs, fonts, strict=True):
            box = self.draw.textbbox((x, baseline), run, font=font, anchor="ls")
            top, bottom = min(top, box[1]), max(bottom, box[3])
            x1 = max(x1, box[2])
            x0 = min(x0, box[0])
            self.draw.text((x, baseline), run, fill=fill, font=font, anchor="ls")
            x += float(self.draw.textlength(run, font=font))
        if x0 < 0 or x1 > WIDTH or bottom > self.height or top < 0:
            self.overflow.append(text)
        elif width is not None and total > width + 0.5:
            self.overflow.append(text)

    def dashed(
        self,
        p: tuple[float, float],
        q: tuple[float, float],
        colour: tuple[int, int, int],
        width: int,
        on: int = 18,
        off: int = 12,
    ) -> None:
        dx, dy = q[0] - p[0], q[1] - p[1]
        length = (dx * dx + dy * dy) ** 0.5
        if length == 0:
            return
        ux, uy = dx / length, dy / length
        d = 0.0
        while d < length:
            e = min(d + on, length)
            self.draw.line(
                [(p[0] + ux * d, p[1] + uy * d), (p[0] + ux * e, p[1] + uy * e)],
                fill=colour,
                width=width,
            )
            d += on + off

    def dashed_rect(self, box: tuple[int, int, int, int], colour: tuple[int, int, int]) -> None:
        x0, y0, x1, y1 = box
        self.dashed((x0, y0), (x1, y0), colour, 3)
        self.dashed((x1, y0), (x1, y1), colour, 3)
        self.dashed((x1, y1), (x0, y1), colour, 3)
        self.dashed((x0, y1), (x0, y0), colour, 3)

    def arrow_head(
        self,
        tip: tuple[float, float],
        frm: tuple[float, float],
        colour: tuple[int, int, int],
    ) -> None:
        dx, dy = tip[0] - frm[0], tip[1] - frm[1]
        length = (dx * dx + dy * dy) ** 0.5 or 1.0
        ux, uy = dx / length, dy / length
        base = (tip[0] - ux * 20, tip[1] - uy * 20)
        left = (base[0] - uy * 10, base[1] + ux * 10)
        right = (base[0] + uy * 10, base[1] - ux * 10)
        self.draw.polygon([tip, left, right], fill=colour)

    def png(self) -> bytes:
        buffer = io.BytesIO()
        self.image.save(buffer, format="PNG", compress_level=6)
        return buffer.getvalue()


def assign_hues(categories: list[str]) -> dict[str, int]:
    """A hue per category, the same for every image of a map: crc picks it, a clash moves on."""
    hues: dict[str, int] = {}
    for category in sorted(set(categories)):
        index = zlib.crc32(category.encode()) % MAX_HUES
        for step in range(MAX_HUES):
            candidate = (index + step) % MAX_HUES
            if candidate not in hues.values():
                index = candidate
                break
        hues[category] = index
    return hues


def hue_of(category: str, hues: dict[str, int]) -> tuple[int, int, int]:
    return HUES[hues.setdefault(category, zlib.crc32(category.encode()) % MAX_HUES)]


def contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    """WCAG 2 contrast ratio between two colours."""

    def lum(c: tuple[int, int, int]) -> float:
        parts = []
        for v in c:
            s = v / 255
            parts.append(s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4)
        return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]

    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# --- images -------------------------------------------------------------------------------------


@dataclass
class RenderedImage:
    kind: str  # "map" | "overview" | "detail"
    name: str
    png: bytes
    width: int
    height: int
    caption: str
    alt: list[str]
    overflow: list[str]
    smallest_text: int
    positions: dict[str, Slot] = field(default_factory=dict)
    pixels: dict[str, tuple[int, int]] = field(default_factory=dict)  # top-left of each card


@dataclass
class MapRender:
    images: list[RenderedImage]
    text: str
    language: str
    rtl: bool
    drawable: bool
    reason: str = ""
    dropped: list[str] = field(default_factory=list)
    positions: dict[str, Slot] = field(default_factory=dict)
    hash: str = ""


def _header(canvas: Canvas, words: dict[str, Any], sub: str, title: str | None = None) -> None:
    canvas.draw.rectangle([0, 0, WIDTH, HEADER_H], fill=HEADER_BG)
    room = WIDTH - 2 * MARGIN - 190
    head = title or words["header"]
    if canvas.rtl:
        canvas.text((WIDTH - MARGIN, 24), head, 44, HEADER_INK, width=room, anchor="ra", bold=True)
        canvas.text((WIDTH - MARGIN, 88), sub, 28, HEADER_SUB, width=room, anchor="ra")
        canvas.text((MARGIN, 24), "Workzap", 30, HEADER_INK)
        return
    size = 44
    while size > 36 and canvas.width_of(head, size) > room:
        size -= 2
    canvas.text((MARGIN, 24), head, size, HEADER_INK, width=room)
    canvas.text((MARGIN, 88), sub, 28, HEADER_SUB, width=room)
    canvas.text((WIDTH - MARGIN, 24), "Workzap", 30, HEADER_INK, anchor="ra")


def _footer(
    canvas: Canvas,
    words: dict[str, Any],
    categories: list[str],
    hues: dict[str, int],
    show_new: bool,
    lang: str = "en",
    has_links: bool = True,
    has_numbers: bool = True,
    top: int | None = None,
) -> int:
    """Spec v1.5, 18.7: the legend lists every category the image shows (none is left out, none is
    cut with an ellipsis) and the footer line appears only when a number is drawn.

    With `top` the legend sits on a white panel starting there; returns the y below its last line.
    """
    rtl = canvas.rtl
    # `step` is +1 left to right and -1 right to left; `edge` is where each row starts.
    step = -1 if rtl else 1
    inset = 20 if top is not None else 0
    edge = WIDTH - MARGIN - inset if rtl else MARGIN + inset
    anchor = "ra" if rtl else "la"
    y = (canvas.height - 250) if top is None else top + 18
    x = edge
    arrows = ((words["legend_owner"], True), (words["legend_guess"], False)) if has_links else ()
    for text, solid in arrows:
        tail = x + step * 60
        if solid:
            canvas.draw.line([(x, y + 14), (tail, y + 14)], fill=ARROW_SOLID, width=4)
        else:
            canvas.dashed((x, y + 14), (tail, y + 14), ARROW_DASH, 4, on=10, off=8)
        colour = ARROW_SOLID if solid else ARROW_DASH
        canvas.arrow_head((tail + step * 2, y + 14), (x + step * 30, y + 14), colour)
        canvas.text((x + step * 76, y), text, MIN_TEXT_PX, INK, anchor=anchor)
        x += step * (76 + int(canvas.width_of(text, MIN_TEXT_PX)) + 36)
    if show_new:
        tag_w = _tag(canvas, x, y - 2, words["new"])
        label_x = x + step * (tag_w + 16)
        canvas.text((label_x, y), words["legend_new"], MIN_TEXT_PX, INK, anchor=anchor)
    if arrows or show_new:
        y += 50
    x = edge
    limit = WIDTH - 2 * MARGIN - 2 * inset - 60
    # More categories than hues: the ones that share a colour share one legend entry, so none is
    # left out and no colour means two things.
    shared: dict[int, list[str]] = {}
    for category in categories:
        shared.setdefault(id(hue_of(category, hues)), []).append(category)
    entries = [(grp[0], " / ".join(grp)) for grp in shared.values()]
    for category, joined in entries if (len(categories) > 1 or has_links) else []:
        label = (
            " / ".join(category_name(c, lang) for c in joined.split(" / "))
            if rtl
            else joined.replace("_", " ")
        )
        parts = label.split()
        while len(parts) > 1 and canvas.width_of(" ".join(parts), MIN_TEXT_PX) > limit:
            parts.pop()  # whole words only: a legend label is never cut with an ellipsis
        label = " ".join(parts)
        w = int(canvas.width_of(label, MIN_TEXT_PX))
        if (x - 28 - w < MARGIN + inset) if rtl else (x + 28 + w > WIDTH - MARGIN - inset):
            x, y = edge, y + 38
        swatch = x - 16 if rtl else x
        canvas.draw.rectangle([swatch, y + 3, swatch + 16, y + 27], fill=hue_of(category, hues))
        canvas.text((x + step * 26, y), label, MIN_TEXT_PX, INK, width=w + 2, anchor=anchor)
        x += step * (26 + w + 28)
    if categories and (len(categories) > 1 or has_links):
        y += 44 if top is not None else 56
    lines = (
        canvas.wrap(words["foot"], MIN_TEXT_PX, WIDTH - 2 * MARGIN - 2 * inset, 3)
        if has_numbers
        else []
    )
    for line in lines:
        canvas.text((edge, y), line, MIN_TEXT_PX, MUTED, width=WIDTH - 2 * MARGIN, anchor=anchor)
        y += 32
    return y


def _footer_height(
    words: dict[str, Any],
    categories: list[str],
    hues: dict[str, int],
    show_new: bool,
    lang: str,
    has_links: bool,
    has_numbers: bool,
    rtl: bool,
) -> int:
    """How tall the legend panel must be: the footer is drawn once on a scratch canvas."""
    scratch = Canvas(MAX_HEIGHT, rtl)
    end = _footer(scratch, words, categories, hues, show_new, lang, has_links, has_numbers, top=0)
    return max(end + 14, 60) if (categories or has_links or has_numbers or show_new) else 0


def _footer_panel(canvas: Canvas, top: int, height: int) -> None:
    if height > 0:
        canvas.draw.rounded_rectangle(
            [MARGIN, top, WIDTH - MARGIN, top + height],
            radius=14,
            fill=CARD,
            outline=(203, 213, 225),
            width=2,
        )


def _tag(canvas: Canvas, x: int, y: int, label: str) -> int:
    """A "New" tag with its left edge at x (right to left: its right edge); returns its width."""
    w = int(canvas.width_of(label, MIN_TEXT_PX)) + 24
    left = x - w if canvas.rtl else x
    canvas.draw.rounded_rectangle([left, y, left + w, y + 34], radius=8, fill=TAG_BG)
    canvas.text((left + 12, y + 3), label, MIN_TEXT_PX, TAG_INK, width=w - 12)
    return w


def _card(
    canvas: Canvas,
    node: Node,
    xy: tuple[int, int],
    hues: dict[str, int],
    words: dict[str, Any],
) -> None:
    x, y = xy
    rtl = canvas.rtl
    box = [x, y, x + CARD_W, y + CARD_H]
    canvas.draw.rounded_rectangle(box, radius=14, fill=CARD, outline=(203, 213, 225), width=2)
    quiet = node.resolved or node.parked
    bar = RESOLVED_BAR if quiet else hue_of(node.category, hues)
    bar_x = x + CARD_W - 14 if rtl else x
    canvas.draw.rounded_rectangle([bar_x, y, bar_x + 14, y + CARD_H], radius=7, fill=bar)
    ink = MUTED if quiet else INK
    inner = CARD_W - 14 - 2 * 18
    tx = x + CARD_W - 32 if rtl else x + 32
    anchor = "ra" if rtl else "la"
    ty = y + 22
    lines = canvas.wrap(node.label, LABEL_PX, inner, 3, bold=rtl)
    for line in lines:
        canvas.text((tx, ty), line, LABEL_PX, ink, width=inner, anchor=anchor, bold=rtl)
        ty += LABEL_PX + 6
    ty = y + 22 + max(2, len(lines)) * (LABEL_PX + 6) + 4
    if node.facts:
        text = " · ".join(node.facts)
        for line in canvas.wrap(text, FACT_PX, inner, MAX_FACT_LINES):
            canvas.text((tx, ty), line, FACT_PX, MUTED, width=inner, anchor=anchor)
            ty += FACT_PX + 6
    tag = words["new"] if node.is_new else (words["stale"] if node.stale else "")
    if tag:
        w = int(canvas.width_of(tag, MIN_TEXT_PX)) + 24
        _tag(canvas, x + 12 + w if rtl else x + CARD_W - w - 12, y - 17, tag)


def _edge_points(
    a: tuple[int, int], b: tuple[int, int]
) -> tuple[tuple[float, float], tuple[float, float], bool]:
    """Where a link leaves card a and enters card b; True when it runs sideways in one row."""
    ax, ay = a
    bx, by = b
    if ay == by:
        y = ay + CARD_H / 2
        if ax < bx:
            return (ax + CARD_W, y), (bx, y), True
        return (ax, y), (bx + CARD_W, y), True
    cx_a, cx_b = ax + CARD_W / 2, bx + CARD_W / 2
    if by > ay:
        return (cx_a, ay + CARD_H), (cx_b, by), False
    return (cx_a, ay), (cx_b, by + CARD_H), False


def _draw_links(
    canvas: Canvas,
    links: list[Link],
    pos: dict[str, tuple[int, int]],
    words: dict[str, Any],
) -> list[tuple[Link, tuple[float, float], bool]]:
    """Arrows go under the cards (drawn first); the labels are drawn after, on top."""
    labels: list[tuple[Link, tuple[float, float], bool]] = []
    for link in links:
        if link.a not in pos or link.b not in pos:
            continue
        p, q, sideways = _edge_points(pos[link.a], pos[link.b])
        colour = ARROW_SOLID if link.solid else ARROW_DASH
        if link.solid:
            canvas.draw.line([p, q], fill=colour, width=4)
        else:
            canvas.dashed(p, q, colour, 4, on=14, off=10)
        directed = link.type not in _PLAIN
        if directed:
            if link.type == "symptom_of":
                canvas.arrow_head(p, q, colour)  # the cause (b) comes first: the arrow ends at a
            else:
                canvas.arrow_head(q, p, colour)
        if sideways:
            mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        else:
            dy = q[1] - p[1]
            step = (GAP_Y / 2) * (1 if dy > 0 else -1)
            t = step / dy if dy else 0.5
            mid = (p[0] + (q[0] - p[0]) * t, p[1] + step)
        labels.append((link, mid, sideways))
    return labels


def _draw_labels(
    canvas: Canvas,
    labels: list[tuple[Link, tuple[float, float], bool]],
    words: dict[str, Any],
) -> None:
    placed: list[tuple[float, float, float, float]] = []
    for link, mid, sideways in labels:
        text = link.label or words["types"].get(link.type, "")
        if not text:
            continue
        width = COL_GAP - 12 if sideways else 380
        lines = canvas.wrap(text, MIN_TEXT_PX, width, 3 if sideways else 1)
        w = max(int(canvas.width_of(ln, MIN_TEXT_PX)) for ln in lines) + 14
        h = 30 * len(lines) + 6
        x0, y0 = mid[0] - w / 2, mid[1] - h / 2
        for _ in range(4):  # two labels on one spot: slide the later one aside
            if not any(not (x0 + w < a or x0 > c or y0 + h < b or y0 > d) for a, b, c, d in placed):
                break
            x0 += w + 10
        x0 = max(4.0, min(x0, WIDTH - w - 4.0))
        placed.append((x0, y0, x0 + w, y0 + h))
        canvas.draw.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=8, fill=BG)
        for n, line in enumerate(lines):
            if canvas.rtl:
                canvas.text((x0 + w - 7, y0 + 3 + 30 * n), line, MIN_TEXT_PX, INK, anchor="ra")
            else:
                canvas.text((x0 + 7, y0 + 3 + 30 * n), line, MIN_TEXT_PX, INK, width=w - 8)


def _outlines(
    canvas: Canvas,
    clusters: list[Cluster],
    pos: dict[str, tuple[int, int]],
    words: dict[str, Any],
) -> None:
    boxes: list[tuple[int, int, int, int]] = []
    for cluster in clusters:
        ids = [i for i in cluster.node_ids if i in pos]
        if len(ids) < 2:
            continue
        x0 = min(pos[i][0] for i in ids) - OUTLINE_PAD
        y0 = min(pos[i][1] for i in ids) - OUTLINE_TITLE
        x1 = max(pos[i][0] for i in ids) + CARD_W + OUTLINE_PAD
        y1 = max(pos[i][1] for i in ids) + CARD_H + OUTLINE_PAD
        outsider = any(
            n not in ids and not (px + CARD_W < x0 or px > x1 or py + CARD_H < y0 or py > y1)
            for n, (px, py) in pos.items()
        )
        clash = any(not (x1 < a or x0 > c or y1 < b or y0 > d) for a, b, c, d in boxes)
        if outsider or clash:
            continue  # an outline that would swallow another problem is worse than none
        boxes.append((x0, y0, x1, y1))
        canvas.dashed_rect((x0, y0, x1, y1), OUTLINE)
        title = words["cluster"].format(title=cluster.title) if cluster.title else ""
        for line in canvas.wrap(title, MIN_TEXT_PX, x1 - x0 - 24, 1):
            if canvas.rtl:
                canvas.text(
                    (x1 - 12, y0 + 8), line, MIN_TEXT_PX, MUTED, anchor="ra", width=x1 - x0 - 24
                )
            else:
                canvas.text((x0 + 12, y0 + 8), line, MIN_TEXT_PX, MUTED, width=x1 - x0 - 24)


def _alt(nodes: list[Node], links: list[Link], words: dict[str, Any]) -> list[str]:
    label = {n.id: n.label for n in nodes}
    out: list[str] = []
    for node in nodes:
        line = words["alt_node"].format(label=node.label)
        if node.facts:
            line += ": " + "; ".join(node.facts[:MAX_FACT_LINES])
        if node.is_new:
            line += f" ({words['new']})"
        elif node.stale:
            line += f" ({words['stale']})"
        out.append(line)
    for link in links:
        if link.a in label and link.b in label:
            kind = words["alt_owner"] if link.solid else words["alt_guess"]
            name = link.label or words["types"].get(link.type, "")
            out.append(
                words["alt_link"].format(a=label[link.a], b=label[link.b], label=name, kind=kind)
            )
    return out


def _render_nodes(
    nodes: list[Node],
    links: list[Link],
    clusters: list[Cluster],
    words: dict[str, Any],
    sub: str,
    previous: dict[str, Slot] | None,
    hues: dict[str, int],
    title: str | None = None,
    rtl: bool = False,
    lang: str = "en",
) -> tuple[Canvas, dict[str, Slot], dict[str, tuple[int, int]]]:
    shown = {n.id for n in nodes}
    clusters = [
        Cluster(c.id, c.title, [i for i in c.node_ids if i in shown])
        for c in clusters
        if len([i for i in c.node_ids if i in shown]) >= 1
    ]
    links = [lk for lk in links if lk.a in shown and lk.b in shown]
    cats: list[str] = []
    for node in nodes:
        if node.category not in cats:
            cats.append(node.category)
    numbered = any(numbers_in(t) for n in nodes for t in (n.label, *n.facts))
    show_new = any(n.is_new for n in nodes)
    footer_h = _footer_height(words, cats, hues, show_new, lang, bool(links), numbered, rtl)
    compact = 2 <= len(nodes) <= COMPACT_MAX_NODES and not any(
        len(c.node_ids) >= 2 for c in clusters
    )
    with _GEO_LOCK:
        if compact:
            saved = _set_geo(
                COLS=1,
                CARD_W=WIDTH - 2 * MARGIN,
                CARD_H=250,
                GAP_Y=80 if links else 36,
                PAD_TOP=24,
                OUTLINE_TITLE=0,
                LABEL_PX=40,
                FACT_PX=30,
            )
        else:
            saved = {}
        try:
            return _draw_nodes(
                nodes, links, clusters, words, sub, previous, hues, title, rtl, lang,
                cats, footer_h, show_new, numbered,
            )  # fmt: skip
        finally:
            _set_geo(**saved)


def _set_geo(**values: int) -> dict[str, int]:
    """Swap the layout constants (compact mode); returns the ones replaced. Hold `_GEO_LOCK`."""
    g = globals()
    old = {k: g[k] for k in values}
    g.update(values)
    return old


def _draw_nodes(
    nodes: list[Node],
    links: list[Link],
    clusters: list[Cluster],
    words: dict[str, Any],
    sub: str,
    previous: dict[str, Slot] | None,
    hues: dict[str, int],
    title: str | None,
    rtl: bool,
    lang: str,
    cats: list[str],
    footer_h: int,
    show_new: bool,
    numbered: bool,
) -> tuple[Canvas, dict[str, Slot], dict[str, tuple[int, int]]]:
    gap_below = 30
    slots = layout(nodes, links, clusters, previous, cluster_rows=True)
    pos, used = _geometry(slots, rtl)
    height = HEADER_H + PAD_TOP + OUTLINE_TITLE + used + gap_below + footer_h + 24
    if height > MAX_HEIGHT:
        slots = layout(nodes, links, clusters, previous, cluster_rows=False)
        pos, used = _geometry(slots, rtl)
        height = HEADER_H + PAD_TOP + OUTLINE_TITLE + used + gap_below + footer_h + 24
    canvas = Canvas(height, rtl)
    _header(canvas, words, sub, title)
    _outlines(canvas, clusters, pos, words)
    labels = _draw_links(canvas, links, pos, words)
    for node in nodes:
        _card(canvas, node, pos[node.id], hues, words)
    _draw_labels(canvas, labels, words)
    panel_top = HEADER_H + PAD_TOP + OUTLINE_TITLE + used + gap_below
    _footer_panel(canvas, panel_top, footer_h)
    _footer(canvas, words, cats, hues, show_new, lang, bool(links), numbered, top=panel_top)
    return canvas, slots, pos


def _bubbles(
    groups: list[tuple[str, list[Node], int]],
    words: dict[str, Any],
    sub: str,
    hues: dict[str, int],
    rtl: bool = False,
    lang: str = "en",
) -> Canvas:
    rows = (len(groups) + 1) // 2
    height = HEADER_H + 40 + rows * 190 + 40 + 270
    canvas = Canvas(height, rtl)
    _header(canvas, words, sub, f"{words['header']}")
    cats: list[str] = []
    for i, (title, members, link_count) in enumerate(groups):
        row, col = divmod(i, 2)
        x = MARGIN + col * (CARD_W + COL_GAP)
        if rtl:
            x = WIDTH - x - CARD_W
        y = HEADER_H + 40 + row * 190
        counts_: dict[str, int] = {}
        for node in members:
            counts_[node.category] = counts_.get(node.category, 0) + 1
            if node.category not in cats:
                cats.append(node.category)
        dominant = sorted(counts_, key=lambda c: (-counts_[c], c))[0]
        canvas.draw.rounded_rectangle([x, y, x + CARD_W, y + 160], radius=24, fill=CARD)
        canvas.dashed_rect((x, y, x + CARD_W, y + 160), OUTLINE)
        bar_x = x + CARD_W - 18 if rtl else x + 4
        canvas.draw.rounded_rectangle(
            [bar_x, y + 4, bar_x + 14, y + 156], radius=6, fill=hue_of(dominant, hues)
        )
        inner = CARD_W - 60
        near = x + CARD_W - 36 if rtl else x + 36  # the side the text starts from
        far = x + 20 if rtl else x + CARD_W - 20
        anchor = "ra" if rtl else "la"
        for n, line in enumerate(canvas.wrap(title, 30, inner, 2, bold=rtl)):
            canvas.text(
                (near, y + 18 + 36 * n), line, 30, INK, width=inner, anchor=anchor, bold=rtl
            )
        count = count_phrase(words, "problem", len(members))
        canvas.text((near, y + 100), count, 28, MUTED, width=inner, anchor=anchor)
        if link_count:
            tail = count_phrase(words, "link", link_count)
            canvas.text((far, y + 100), tail, 28, MUTED, anchor="la" if rtl else "ra", width=170)
    _footer(canvas, words, cats, hues, False, lang, False, False)
    return canvas


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _group_clusters(prep: Prepared, words: dict[str, Any]) -> list[Cluster]:
    """Every problem in exactly one cluster; those in none go to a closing 'other problems' one."""
    seen: set[str] = set()
    out: list[Cluster] = []
    for cluster in prep.clusters:
        ids = [i for i in cluster.node_ids if i not in seen]
        seen.update(ids)
        if ids:
            out.append(Cluster(cluster.id, cluster.title or words["others"], ids))
    rest = [n.id for n in prep.nodes if n.id not in seen]
    if rest:
        out.append(Cluster("_other", words["others"], rest))
    return out


# --- text fallback ------------------------------------------------------------------------------


def text_fallback(
    map_: dict[str, Any], language: str | None = None, said: set[str] | None = None
) -> str:
    """The map as a short list with arrows in words: "Maal ruka -> paisa phansa -> ...".

    Safe for any script (the words are the owner's own); right to left languages get the arrow the
    other way round so it still reads from cause to effect.
    """
    lang = _lang(language)
    words = _words(lang)
    rtl = is_rtl(language)
    arrow = "←" if rtl else "→"
    prep = _prepare(map_, said)
    stale = f" ({words['stale']})"
    name = {n.id: n.label + (stale if n.stale else "") for n in prep.nodes}
    solid = {(lk.a, lk.b): lk.solid for lk in prep.links}
    # cause first: a symptom_of link points at the cause, so flip it
    edges: list[tuple[str, str]] = []
    for lk in prep.links:
        edges.append((lk.b, lk.a) if lk.type == "symptom_of" else (lk.a, lk.b))
    used: set[tuple[str, str]] = set()
    incoming = {b for _, b in edges}
    starts = [a for a, _ in edges if a not in incoming]
    for a, _ in edges:  # cycles: start anywhere, in input order
        if a not in starts:
            starts.append(a)
    lines: list[str] = []
    linked: set[str] = set()
    for start in starts:
        while True:
            chain = [start]
            guess = False
            cur = start
            while True:
                nxt = next(((a, b) for a, b in edges if a == cur and (a, b) not in used), None)
                if nxt is None:
                    break
                used.add(nxt)
                guess = guess or not solid.get(nxt, solid.get((nxt[1], nxt[0]), True))
                chain.append(nxt[1])
                cur = nxt[1]
                if len(chain) > len(name) + 1:
                    break
            if len(chain) == 1:
                break
            linked.update(chain)
            line = f" {arrow} ".join(name[i] for i in chain)
            if guess:
                line += f" {words.get('guess_note', TEXT['en']['guess_note'])}"
            lines.append(line)
    alone = [name[n.id] for n in prep.nodes if n.id not in linked]
    out = [str(words["header"]), ""]
    out.append(
        str(words["summary"]).format(
            **counts(words, prep.version, len(prep.nodes), len(prep.links))
        )
    )
    out += [f"- {line}" for line in lines]
    out += [f"- {label}" for label in alone]
    out += ["", str(words["foot"])]
    return "\n".join(out)


# --- the entry point ----------------------------------------------------------------------------


def _drawable_text(prep: Prepared) -> bool:
    def ok(text: str) -> bool:
        return all(ord(c) < 0x250 or c in _LATIN_PUNCT for c in text)

    for n in prep.nodes:
        if not all(ok(t) for t in [n.label, *n.facts]):
            return False
    return all(ok(lk.label) for lk in prep.links) and all(ok(c.title) for c in prep.clusters)


def _rtl_drawable_text(prep: Prepared, words: dict[str, Any]) -> bool:
    """Every word of the map, and the language's own wording, has a glyph in Naskh or Latin."""
    texts = [t for n in prep.nodes for t in [n.label, *n.facts]]
    texts += [lk.label for lk in prep.links] + [c.title for c in prep.clusters]
    for value in words.values():
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, dict):
            texts += [v for v in value.values() if isinstance(v, str)]
    return all(rtl_drawable(t) for t in texts if t)


def render_map(
    map_: dict[str, Any],
    language: str | None = "roman_ur",
    previous: dict[str, Slot] | None = None,
    owner_messages: list[str] | None = None,
) -> MapRender:
    """Draw the map. `images` is empty (and `reason` says why) when only the text can be sent.

    `previous` is the `positions` of the version before: problems in it keep their place.
    `owner_messages`, when given, stops any number the owner never wrote from being drawn.
    Right-to-left languages are drawn mirrored with the Naskh font; if the font or the shaping
    packages are missing, `reason` starts with "rtl_support_missing" and only the text is returned.
    """
    lang = _lang(language)
    rtl = is_rtl(language)
    said: set[str] | None = None
    if owner_messages is not None:
        said = set()
        for message in owner_messages:
            said.update(numbers_in(message))
    prep = _prepare(map_, said)
    text = text_fallback(map_, language, said)
    digest = map_hash(map_, lang)
    result = MapRender([], text, lang, rtl, False, dropped=prep.dropped, hash=digest)
    if lang not in DRAWABLE_LANGUAGES:
        result.reason = "unsupported_language"
        return result
    if not prep.nodes:
        result.reason = "empty_map"
        return result
    words = _words(lang)
    if rtl:
        try:
            _load_rtl()
            drawable = _rtl_drawable_text(prep, words)
        except (ImportError, OSError) as error:
            result.reason = f"rtl_support_missing: {type(error).__name__}: {error}"
            return result
        if not drawable:
            result.reason = "text_not_drawable_in_naskh_font"
            return result
    elif not _drawable_text(prep):
        result.reason = "text_not_drawable_in_latin_font"
        return result
    try:
        _draw_all(result, prep, words, lang, rtl, previous)
    except (ImportError, OSError) as error:
        result.images, result.positions, result.drawable = [], {}, False
        result.reason = f"rtl_support_missing: {type(error).__name__}: {error}"
    return result


def _draw_all(
    result: MapRender,
    prep: Prepared,
    words: dict[str, Any],
    lang: str,
    rtl: bool,
    previous: dict[str, Slot] | None,
) -> None:
    result.drawable = True
    hues = assign_hues([n.category for n in prep.nodes])
    fields = counts(words, prep.version, len(prep.nodes), len(prep.links))
    full_sub = str(words["summary"]).format(**fields)
    if len(prep.nodes) <= MAX_NODES:
        canvas, slots, pixels = _render_nodes(
            prep.nodes, prep.links, prep.clusters, words, full_sub, previous, hues, None, rtl, lang
        )
        result.images.append(
            RenderedImage(
                "map",
                f"map-v{prep.version}",
                canvas.png(),
                WIDTH,
                canvas.height,
                str(words["caption"]).format(**fields),
                _alt(prep.nodes, prep.links, words),
                canvas.overflow,
                canvas.smallest,
                slots,
                pixels,
            )
        )
        result.positions = slots
        return

    groups = _group_clusters(prep, words)
    by_id = {n.id: n for n in prep.nodes}
    members_of = {c.id: [by_id[i] for i in c.node_ids] for c in groups}

    def inside(cluster: Cluster) -> int:
        ids = set(cluster.node_ids)
        return sum(1 for lk in prep.links if lk.a in ids and lk.b in ids)

    version = f"{words['version']} {prep.version}"
    bubble_rows = [(c.title, members_of[c.id], inside(c)) for c in groups]
    for part, chunk in enumerate(_chunks(bubble_rows, MAX_BUBBLES), 1):
        sub = f"{version} · {words['overview']}"
        if len(bubble_rows) > MAX_BUBBLES:
            sub += f" {part}"
        canvas = _bubbles(chunk, words, sub, hues, rtl, lang)
        caption = str(words["caption_overview"]).format(
            version=words["version"], v=prep.version, k=len(groups)
        )
        alt = [f"{t}: {count_phrase(words, 'problem', len(m))}" for t, m, _ in chunk]
        result.images.append(
            RenderedImage(
                "overview",
                f"overview-v{prep.version}-{part}",
                canvas.png(),
                WIDTH,
                canvas.height,
                caption,
                alt,
                canvas.overflow,
                canvas.smallest,
            )
        )
    for cluster in groups:
        nodes = members_of[cluster.id]
        for part, chunk in enumerate(_chunks(nodes, MAX_NODES), 1):
            ids = {n.id for n in chunk}
            sub_links = [lk for lk in prep.links if lk.a in ids and lk.b in ids]
            sub = f"{version} · {cluster.title}"
            if len(nodes) > MAX_NODES:
                sub += f" ({part}/{len(_chunks(nodes, MAX_NODES))})"
            canvas, slots, pixels = _render_nodes(
                chunk,
                sub_links,
                [],
                words,
                sub,
                previous,
                hues,
                title=str(words["cluster"]).format(title=cluster.title)
                if cluster.id != "_other"
                else str(words["others"]),
                rtl=rtl,
                lang=lang,
            )
            caption = str(words["caption_detail"]).format(
                version=words["version"],
                v=prep.version,
                title=cluster.title,
                pc=count_phrase(words, "problem", len(chunk)),
            )
            result.images.append(
                RenderedImage(
                    "detail",
                    f"detail-v{prep.version}-{cluster.id}-{part}",
                    canvas.png(),
                    WIDTH,
                    canvas.height,
                    caption,
                    _alt(chunk, sub_links, words),
                    canvas.overflow,
                    canvas.smallest,
                    slots,
                    pixels,
                )
            )
            result.positions.update(slots)
