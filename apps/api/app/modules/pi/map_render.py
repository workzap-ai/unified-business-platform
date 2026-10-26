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

Scripts. The font is Pillow's bundled Latin font. Pillow here has no raqm (complex text layout)
and the project has neither `arabic_reshaper` nor `python-bidi`, so Urdu, Arabic and Persian script
cannot be shaped: those languages (and any map whose words the font cannot draw) get the text
fallback only, written right to left, never a badly shaped picture. See `NEEDS_FOR_RTL_IMAGES`.

Safety: every drawn word passes the project's redactor, long digit runs, e-mail addresses and
links are removed, and when the owner's messages are supplied a number the owner never said is not
drawn (`numbers_supported` checks the same thing for a whole map).
"""

import hashlib
import io
import json
import re
import zlib
from dataclasses import dataclass, field
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.modules.pi import safety

WIDTH = 1080
MIN_HEIGHT = 1350
MAX_HEIGHT = 1920
MAX_NODES = 9
MAX_BUBBLES = 12
MAX_HUES = 5
MIN_TEXT_PX = 24
MAX_PNG_BYTES = 5 * 1024 * 1024
MAX_LABEL_WORDS = 6
MAX_LINK_WORDS = 3
MAX_FACT_LINES = 3

DRAWABLE_LANGUAGES = ("en", "roman_ur")
RTL_LANGUAGES = ("ur", "ar", "fa", "ps", "sd")
NEEDS_FOR_RTL_IMAGES = (
    "a Naskh-capable font file (Noto Naskh Arabic, SIL OFL 1.1) vendored into the repo, and either "
    "Pillow built with raqm (libraqm, fribidi, harfbuzz) or the arabic_reshaper and python-bidi "
    "packages added to pyproject.toml"
)

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
        "summary": "Version {v} · {n} {problems} · {l} {links}",
        "problem": "problem",
        "problems": "problems",
        "link": "link",
        "links": "links",
        "new": "New",
        "legend_owner": "You said it",
        "legend_guess": "My guess",
        "legend_new": "added",
        "foot": "Only the numbers you gave are used. No names or personal details.",
        "overview": "Overview",
        "cluster": "One root: {title}",
        "others": "Other problems",
        "more": "More below",
        "caption": "Version {v}: {n} {problems}, {l} {links}.",
        "caption_overview": "Version {v}, overview: {k} groups.",
        "caption_detail": "Version {v}, {title}: {n} {problems}.",
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
        "summary": "Version {v} · {n} {problems} · {l} {links}",
        "problem": "masla",
        "problems": "masle",
        "link": "jorr",
        "links": "jorr",
        "new": "Naya",
        "legend_owner": "Aap ne bataya",
        "legend_guess": "Hamara andaza",
        "legend_new": "naya",
        "foot": "Sirf aap ke bataye hue number. Koi naam ya zaati tafseel nahi.",
        "overview": "Mukhtasar naqsha",
        "cluster": "Ek hi jar: {title}",
        "others": "Baqi masle",
        "more": "Aage dekhein",
        "caption": "Version {v}: {n} {problems}, {l} {links}.",
        "caption_overview": "Version {v}, mukhtasar: {k} hisse.",
        "caption_detail": "Version {v}, {title}: {n} {problems}.",
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
    # Urdu script: text fallback only (see the module note on scripts).
    "ur": {
        "header": "آپ کے کاروبار کا نقشہ",
        "summary": "ورژن {v} · {n} مسئلے · {l} جوڑ",
        "foot": "صرف آپ کے بتائے ہوئے نمبر۔ کوئی نام یا ذاتی تفصیل نہیں۔",
        "guess_note": "(ہمارا اندازہ)",
    },
}


def _words(language: str | None) -> dict[str, Any]:
    return TEXT.get(language or "en", TEXT["en"])


def is_rtl(language: str | None) -> bool:
    return (language or "").split("-")[0].lower() in RTL_LANGUAGES


def _lang(language: str | None) -> str:
    base = (language or "en").split("-")[0].lower()
    return base if base in ("en", "roman_ur", "ur") else ("ur" if base in RTL_LANGUAGES else "en")


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
COL_GAP = 120
MARGIN = 40
GAP_Y = 80
HEADER_H = 150
PAD_TOP = 30
OUTLINE_PAD = 14
OUTLINE_TITLE = 44
COLS = 2

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


def _geometry(slots: dict[str, Slot]) -> tuple[dict[str, tuple[int, int]], int]:
    """Top-left pixel of every card (empty rows squeezed out) and the height the cards use."""
    rows = sorted({s[0] for s in slots.values()})
    row_index = {r: i for i, r in enumerate(rows)}
    alone = {r: sum(1 for s in slots.values() if s[0] == r) == 1 for r in rows}
    pos: dict[str, tuple[int, int]] = {}
    for nid, (row, col) in slots.items():
        x = MARGIN + col * (CARD_W + COL_GAP)
        if alone[row]:
            x = (WIDTH - CARD_W) // 2
        pos[nid] = (x, HEADER_H + PAD_TOP + OUTLINE_TITLE + row_index[row] * (CARD_H + GAP_Y))
    used = len(rows) * CARD_H + max(0, len(rows) - 1) * GAP_Y
    return pos, used


# --- drawing primitives -------------------------------------------------------------------------


def _font(size: int) -> Any:
    return ImageFont.load_default(size=max(size, MIN_TEXT_PX))


class Canvas:
    """A PNG being drawn. Records every text that does not fit its box or leaves the image."""

    def __init__(self, height: int) -> None:
        self.height = max(MIN_HEIGHT, min(height, MAX_HEIGHT))
        self.image = Image.new("RGB", (WIDTH, self.height), BG)
        self.draw = ImageDraw.Draw(self.image)
        self.overflow: list[str] = []
        self.smallest = 10_000

    def width_of(self, text: str, size: int) -> float:
        return float(self.draw.textlength(text, font=_font(size)))

    def wrap(self, text: str, size: int, width: int, max_lines: int) -> list[str]:
        """Lines that fit `width`; the last ends with an ellipsis when the text is cut."""
        font = _font(size)
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            while self.draw.textlength(word, font=font) > width:  # one very long word
                cut = len(word)
                while cut > 1 and self.draw.textlength(word[:cut], font=font) > width:
                    cut -= 1
                if current:
                    lines.append(current)
                    current = ""
                lines.append(word[:cut])
                word = word[cut:]
            trial = f"{current} {word}".strip()
            if current and self.draw.textlength(trial, font=font) > width:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            last = lines[-1]
            while last and self.draw.textlength(last + "…", font=font) > width:
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
    ) -> None:
        font = _font(size)
        self.smallest = min(self.smallest, max(size, MIN_TEXT_PX))
        box = self.draw.textbbox(xy, text, font=font, anchor=anchor)
        if box[0] < 0 or box[2] > WIDTH or box[3] > self.height or box[1] < 0:
            self.overflow.append(text)
        elif width is not None and (box[2] - box[0]) > width + 0.5:
            self.overflow.append(text)
        self.draw.text(xy, text, fill=fill, font=font, anchor=anchor)

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
    canvas.text(
        (MARGIN, 24), title or words["header"], 44, HEADER_INK, width=WIDTH - 2 * MARGIN - 190
    )
    canvas.text((MARGIN, 88), sub, 28, HEADER_SUB, width=WIDTH - 2 * MARGIN - 190)
    canvas.text((WIDTH - MARGIN, 24), "Workzap", 30, HEADER_INK, anchor="ra")


def _footer(
    canvas: Canvas,
    words: dict[str, Any],
    categories: list[str],
    hues: dict[str, int],
    show_new: bool,
) -> None:
    top = canvas.height - 250
    y = top
    x = MARGIN
    canvas.draw.line([(x, y + 14), (x + 60, y + 14)], fill=ARROW_SOLID, width=4)
    canvas.arrow_head((x + 62, y + 14), (x + 30, y + 14), ARROW_SOLID)
    canvas.text((x + 76, y), words["legend_owner"], MIN_TEXT_PX, INK)
    x += 76 + int(canvas.width_of(words["legend_owner"], MIN_TEXT_PX)) + 36
    canvas.dashed((x, y + 14), (x + 60, y + 14), ARROW_DASH, 4, on=10, off=8)
    canvas.arrow_head((x + 62, y + 14), (x + 30, y + 14), ARROW_DASH)
    canvas.text((x + 76, y), words["legend_guess"], MIN_TEXT_PX, INK)
    x += 76 + int(canvas.width_of(words["legend_guess"], MIN_TEXT_PX)) + 36
    if show_new:
        _tag(canvas, x, y - 2, words["new"])
        canvas.text((x + 100, y), words["legend_new"], MIN_TEXT_PX, INK)
    y += 50
    x = MARGIN
    for category in categories[:MAX_HUES]:
        label = category.replace("_", " ")
        label = canvas.wrap(label, MIN_TEXT_PX, 210, 1)[0] if label else label
        w = int(canvas.width_of(label, MIN_TEXT_PX))
        if x + 28 + w > WIDTH - MARGIN:
            x, y = MARGIN, y + 38
        canvas.draw.rectangle([x, y + 3, x + 16, y + 27], fill=hue_of(category, hues))
        canvas.text((x + 26, y), label, MIN_TEXT_PX, INK, width=w + 2)
        x += 26 + w + 28
    y += 56
    lines = canvas.wrap(words["foot"], MIN_TEXT_PX, WIDTH - 2 * MARGIN, 3)
    for line in lines:
        canvas.text((MARGIN, y), line, MIN_TEXT_PX, MUTED, width=WIDTH - 2 * MARGIN)
        y += 32


def _tag(canvas: Canvas, x: int, y: int, label: str) -> None:
    w = int(canvas.width_of(label, MIN_TEXT_PX)) + 24
    canvas.draw.rounded_rectangle([x, y, x + w, y + 34], radius=8, fill=TAG_BG)
    canvas.text((x + 12, y + 3), label, MIN_TEXT_PX, TAG_INK, width=w - 12)


def _card(
    canvas: Canvas,
    node: Node,
    xy: tuple[int, int],
    hues: dict[str, int],
    words: dict[str, Any],
) -> None:
    x, y = xy
    box = [x, y, x + CARD_W, y + CARD_H]
    canvas.draw.rounded_rectangle(box, radius=14, fill=CARD, outline=(203, 213, 225), width=2)
    bar = RESOLVED_BAR if node.resolved else hue_of(node.category, hues)
    canvas.draw.rounded_rectangle([x, y, x + 14, y + CARD_H], radius=7, fill=bar)
    ink = MUTED if node.resolved else INK
    inner = CARD_W - 14 - 2 * 18
    ty = y + 22
    for line in canvas.wrap(node.label, 30, inner, 2):
        canvas.text((x + 32, ty), line, 30, ink, width=inner)
        ty += 36
    ty = y + 22 + 2 * 36 + 4
    if node.facts:
        text = " · ".join(node.facts)
        for line in canvas.wrap(text, MIN_TEXT_PX, inner, MAX_FACT_LINES):
            canvas.text((x + 32, ty), line, MIN_TEXT_PX, MUTED, width=inner)
            ty += 30
    if node.is_new:
        w = int(canvas.width_of(words["new"], MIN_TEXT_PX)) + 24
        _tag(canvas, x + CARD_W - w - 12, y - 17, words["new"])


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
) -> tuple[Canvas, dict[str, Slot]]:
    shown = {n.id for n in nodes}
    clusters = [
        Cluster(c.id, c.title, [i for i in c.node_ids if i in shown])
        for c in clusters
        if len([i for i in c.node_ids if i in shown]) >= 1
    ]
    links = [lk for lk in links if lk.a in shown and lk.b in shown]
    footer_h = 270
    slots = layout(nodes, links, clusters, previous, cluster_rows=True)
    pos, used = _geometry(slots)
    height = HEADER_H + PAD_TOP + OUTLINE_TITLE + used + 40 + footer_h
    if height > MAX_HEIGHT:
        slots = layout(nodes, links, clusters, previous, cluster_rows=False)
        pos, used = _geometry(slots)
        height = HEADER_H + PAD_TOP + OUTLINE_TITLE + used + 40 + footer_h
    canvas = Canvas(height)
    _header(canvas, words, sub, title)
    _outlines(canvas, clusters, pos, words)
    labels = _draw_links(canvas, links, pos, words)
    for node in nodes:
        _card(canvas, node, pos[node.id], hues, words)
    _draw_labels(canvas, labels, words)
    cats: list[str] = []
    for node in nodes:
        if node.category not in cats:
            cats.append(node.category)
    _footer(canvas, words, cats, hues, any(n.is_new for n in nodes))
    return canvas, slots


def _bubbles(
    groups: list[tuple[str, list[Node], int]],
    words: dict[str, Any],
    sub: str,
    hues: dict[str, int],
) -> Canvas:
    rows = (len(groups) + 1) // 2
    height = HEADER_H + 40 + rows * 190 + 40 + 270
    canvas = Canvas(height)
    _header(canvas, words, sub, f"{words['header']}")
    cats: list[str] = []
    for i, (title, members, link_count) in enumerate(groups):
        row, col = divmod(i, 2)
        x = MARGIN + col * (CARD_W + COL_GAP)
        y = HEADER_H + 40 + row * 190
        counts: dict[str, int] = {}
        for node in members:
            counts[node.category] = counts.get(node.category, 0) + 1
            if node.category not in cats:
                cats.append(node.category)
        dominant = sorted(counts, key=lambda c: (-counts[c], c))[0]
        canvas.draw.rounded_rectangle([x, y, x + CARD_W, y + 160], radius=24, fill=CARD)
        canvas.dashed_rect((x, y, x + CARD_W, y + 160), OUTLINE)
        canvas.draw.rounded_rectangle(
            [x + 4, y + 4, x + 18, y + 156], radius=6, fill=hue_of(dominant, hues)
        )
        inner = CARD_W - 60
        for n, line in enumerate(canvas.wrap(title, 30, inner, 2)):
            canvas.text((x + 36, y + 18 + 36 * n), line, 30, INK, width=inner)
        count = f"{len(members)} {words['problems'] if len(members) != 1 else words['problem']}"
        canvas.text((x + 36, y + 100), count, 28, MUTED, width=inner)
        if link_count:
            tail = f"{link_count} {words['links'] if link_count != 1 else words['link']}"
            canvas.text((x + CARD_W - 20, y + 100), tail, 28, MUTED, anchor="ra", width=170)
    _footer(canvas, words, cats, hues, False)
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
    name = {n.id: n.label for n in prep.nodes}
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
    alone = [n.label for n in prep.nodes if n.id not in linked]
    out = [str(words["header"]), ""]
    out.append(
        str(words["summary"]).format(
            v=prep.version,
            n=len(prep.nodes),
            l=len(prep.links),
            problems=words.get("problems", ""),
            links=words.get("links", ""),
        )
    )
    out += [f"- {line}" for line in lines]
    out += [f"- {label}" for label in alone]
    out += ["", str(words["foot"])]
    return "\n".join(out)


# --- the entry point ----------------------------------------------------------------------------


def _drawable_text(prep: Prepared) -> bool:
    def ok(text: str) -> bool:
        return all(ord(c) < 0x250 or c in "–—‘’“”…·" for c in text)

    for n in prep.nodes:
        if not all(ok(t) for t in [n.label, *n.facts]):
            return False
    return all(ok(lk.label) for lk in prep.links) and all(ok(c.title) for c in prep.clusters)


def render_map(
    map_: dict[str, Any],
    language: str | None = "roman_ur",
    previous: dict[str, Slot] | None = None,
    owner_messages: list[str] | None = None,
) -> MapRender:
    """Draw the map. `images` is empty (and `reason` says why) when only the text can be sent.

    `previous` is the `positions` of the version before: problems in it keep their place.
    `owner_messages`, when given, stops any number the owner never wrote from being drawn.
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
    if rtl or lang not in DRAWABLE_LANGUAGES:
        result.reason = "rtl_script_needs_font_and_shaping" if rtl else "unsupported_language"
        return result
    if not prep.nodes:
        result.reason = "empty_map"
        return result
    if not _drawable_text(prep):
        result.reason = "text_not_drawable_in_latin_font"
        return result
    result.drawable = True
    words = _words(lang)
    hues = assign_hues([n.category for n in prep.nodes])
    full_sub = str(words["summary"]).format(
        v=prep.version,
        n=len(prep.nodes),
        l=len(prep.links),
        problems=words["problems"] if len(prep.nodes) != 1 else words["problem"],
        links=words["links"] if len(prep.links) != 1 else words["link"],
    )
    if len(prep.nodes) <= MAX_NODES:
        canvas, slots = _render_nodes(
            prep.nodes, prep.links, prep.clusters, words, full_sub, previous, hues
        )
        caption = str(words["caption"]).format(
            v=prep.version,
            n=len(prep.nodes),
            l=len(prep.links),
            problems=words["problems"] if len(prep.nodes) != 1 else words["problem"],
            links=words["links"] if len(prep.links) != 1 else words["link"],
        )
        result.images.append(
            RenderedImage(
                "map",
                f"map-v{prep.version}",
                canvas.png(),
                WIDTH,
                canvas.height,
                caption,
                _alt(prep.nodes, prep.links, words),
                canvas.overflow,
                canvas.smallest,
                slots,
            )
        )
        result.positions = slots
        return result

    groups = _group_clusters(prep, words)
    by_id = {n.id: n for n in prep.nodes}
    members_of = {c.id: [by_id[i] for i in c.node_ids] for c in groups}

    def inside(cluster: Cluster) -> int:
        ids = set(cluster.node_ids)
        return sum(1 for lk in prep.links if lk.a in ids and lk.b in ids)

    bubble_rows = [(c.title, members_of[c.id], inside(c)) for c in groups]
    for part, chunk in enumerate(_chunks(bubble_rows, MAX_BUBBLES), 1):
        sub = f"Version {prep.version} · {words['overview']}"
        if len(bubble_rows) > MAX_BUBBLES:
            sub += f" {part}"
        canvas = _bubbles(chunk, words, sub, hues)
        caption = str(words["caption_overview"]).format(v=prep.version, k=len(groups))
        alt = [f"{t}: {len(m)} {words['problems']}" for t, m, _ in chunk]
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
            sub = f"Version {prep.version} · {cluster.title}"
            if len(nodes) > MAX_NODES:
                sub += f" ({part}/{len(_chunks(nodes, MAX_NODES))})"
            canvas, slots = _render_nodes(
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
            )
            caption = str(words["caption_detail"]).format(
                v=prep.version, title=cluster.title, n=len(chunk), problems=words["problems"]
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
                )
            )
            result.positions.update(slots)
    return result
