"""Showing the person their problems (pi Brain spec 8.11.2): the board and the progress card.

Both are PNGs drawn on the server from the problem records, behind a signed, expiring link that
names one conversation and carries no details. The text summary is always sent too. A visual
follows every rule the chat does: it never pitches while pi is listening, it shows no price, it
never names the business (a profile can be filled from a staff record, and only a name the person
gave in the chat would do), and it is sent only as part of a reply inside the 24-hour window.
The picture is drawn with a Latin-script font, so Arabic and Urdu script get the text summary
only: a badly shaped line would be worse than none.
"""

import base64
import hmac
import io
import json
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from PIL import Image, ImageDraw, ImageFont

from app.core.config import Settings
from app.modules.pi import taxonomy
from app.modules.pi_customer.access import _sign

VISUAL_SECONDS = 7 * 86400
KINDS = ("board", "progress")
LANGUAGES = ("en", "roman_ur")  # the scripts the font can draw
WIDTH = 1080
MARGIN = 56
MAX_GROUPS = 8
MAX_WORDS_SHOWN = 2
LIST_ROWS = 10  # a WhatsApp list message holds at most ten rows

INK, MUTED, PAPER, CARD, ACCENT, DONE = (
    (28, 25, 23),
    (112, 104, 96),
    (250, 248, 245),
    (255, 255, 255),
    (232, 93, 48),
    (46, 139, 87),
)

TEXT: dict[str, dict[str, Any]] = {
    "en": {
        "board": "What I've noted so far",
        "board_sub": "Sorted by area. None of it is solved yet.",
        "for": "for {name}",
        "problem": "problem",
        "problems": "problems",
        "board_foot": "Tap the list below to correct anything.",
        "caption": "The same list, as a picture.",
        "list_button": "Correct one",
        "progress": "Where things stand",
        "steps": ["Sorted", "Preparing", "Your decision", "Build"],
        "progress_foot": "You decide what happens next.",
        "progress_caption": "Where things stand.",
    },
    "roman_ur": {
        "board": "Ab tak jo maine note kiya",
        "board_sub": "Hisson mein sort kiya hai. Inme se abhi kuch hal nahi hua.",
        "for": "{name} ke liye",
        "problem": "masla",
        "problems": "masail",
        "board_foot": "Kuch ghalat ho to neeche list se chunein.",
        "caption": "Wahi list, tasveer ki shakal mein.",
        "list_button": "Theek karein",
        "progress": "Kaam kahan tak pohancha",
        "steps": ["Sort ho gaya", "Tayyari", "Aap ka faisla", "Kaam shuru"],
        "progress_foot": "Aage kya hoga, ye aap tay karte hain.",
        "progress_caption": "Kaam kahan tak pohancha.",
    },
}


def supported(language: str | None) -> bool:
    return (language or "en") in LANGUAGES


@dataclass
class Group:
    label: str
    count: int
    words: list[str] = field(default_factory=list)


def token(
    settings: Settings, conversation_id: UUID, kind: str, language: str, step: int = 0
) -> str:
    data = json.dumps(
        {
            "c": str(conversation_id),
            "k": kind,
            "l": language,
            "s": step,
            "e": int(time.time()) + VISUAL_SECONDS,
        },
        separators=(",", ":"),
    ).encode()
    return f"{base64.urlsafe_b64encode(data).decode().rstrip('=')}.{_sign(settings, data)}"


def read(settings: Settings, value: str) -> dict[str, Any] | None:
    """What a token names, or None when it is forged, malformed or expired."""
    try:
        body, mac = value.split(".", 1)
        data = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        if not hmac.compare_digest(mac, _sign(settings, data)):
            return None
        claims = json.loads(data)
        if int(claims["e"]) < time.time() or claims["k"] not in KINDS:
            return None
        language = str(claims.get("l") or "en")
        return {
            "conversation_id": UUID(claims["c"]),
            "kind": claims["k"],
            "language": language if language in LANGUAGES else "en",
            "step": max(0, min(3, int(claims.get("s") or 0))),
        }
    except (ValueError, KeyError, TypeError):
        return None


def url(settings: Settings, value: str, kind: str) -> str:
    base = settings.pi_app_public_url.rstrip("/")
    return f"{base}/api/v1/pi-app/brain-visuals/{value}/{kind}.png"


def _drawable(text: str) -> bool:
    """The Latin font can draw it (Arabic and Urdu script came out as empty boxes)."""
    return all(ord(c) < 0x250 or c in "–—‘’“”…" for c in text)


def _drawable_words(rows: list[Any]) -> list[str]:
    """The person's own words for each problem, without the quote marks they were stored with and
    never in a script the font cannot draw: the problem's title stands in for those."""
    out: list[str] = []
    for problem in rows:
        for raw in (problem.user_words or [])[:1]:
            word = str(raw).strip().strip("\"'“”‘’ ").strip()
            if word and not _drawable(word):
                word = str(getattr(problem, "title", "") or "").strip()
            if word and word not in out:
                out.append(word)
    return out


def groups_of(problems: list[Any], language: str) -> list[Group]:
    """Problems grouped by area, biggest group first, with the person's own words."""
    by_area: dict[str, list[Any]] = {}
    for problem in problems:
        by_area.setdefault(problem.category, []).append(problem)
    order = sorted(by_area, key=lambda c: (-len(by_area[c]), c == taxonomy.OTHER, c))
    out: list[Group] = []
    for category in order[:MAX_GROUPS]:
        rows = by_area[category]
        words = _drawable_words(rows)
        out.append(Group(taxonomy.label(category, language), len(rows), words[:MAX_WORDS_SHOWN]))
    return out


def list_rows(problems: list[Any]) -> list[dict[str, str]]:
    """One WhatsApp list row per problem (at most ten): the title is what comes back when tapped."""
    return [
        {"id": f"p{n}", "title": str(p.title)[:24].rstrip(), "description": str(p.title)[:72]}
        for n, p in enumerate(problems[:LIST_ROWS], 1)
    ]


# --- drawing -----------------------------------------------------------------------------------


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: Any, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if current and draw.textlength(trial, font=font) > width:
            lines.append(current)
            current = word
        else:
            current = trial
    return [*lines, current] if current else lines


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def render_board(groups: list[Group], language: str, business: str | None = None) -> bytes:
    """The problem board: one card per area with its count and the person's own words."""
    words = TEXT.get(language, TEXT["en"])
    title, body, small = _font(54), _font(34), _font(28)
    probe = ImageDraw.Draw(Image.new("RGB", (WIDTH, 10)))
    inner = WIDTH - 2 * MARGIN - 48
    cards: list[tuple[Group, list[str]]] = []
    for group in groups:
        quotes = [
            line for w in group.words for line in _wrap(probe, f"“{w[:80]}”", small, inner)[:2]
        ]
        cards.append((group, quotes))
    height = 300 + sum(120 + 38 * len(q) for _, q in cards) + 120
    image = Image.new("RGB", (WIDTH, max(height, 520)), PAPER)
    draw = ImageDraw.Draw(image)
    draw.text((MARGIN, 48), "pi", fill=ACCENT, font=_font(46))
    draw.text((MARGIN, 112), words["board"], fill=INK, font=title)
    draw.text((MARGIN, 186), words["board_sub"], fill=MUTED, font=small)
    if business:
        draw.text((MARGIN, 228), words["for"].format(name=business[:40]), fill=MUTED, font=small)
    y = 290
    for group, quotes in cards:
        card_height = 100 + 38 * len(quotes)
        draw.rounded_rectangle(
            (MARGIN, y, WIDTH - MARGIN, y + card_height),
            radius=24,
            fill=CARD,
            outline=(232, 226, 218),
        )
        noun = words["problem"] if group.count == 1 else words["problems"]
        draw.text((MARGIN + 24, y + 22), group.label[:34], fill=INK, font=body)
        label = f"{group.count} {noun}"
        draw.text(
            (WIDTH - MARGIN - 24 - draw.textlength(label, font=small), y + 28),
            label,
            fill=ACCENT,
            font=small,
        )
        for n, line in enumerate(quotes):
            draw.text((MARGIN + 24, y + 78 + 38 * n), line, fill=MUTED, font=small)
        y += card_height + 20
    draw.text((MARGIN, y + 24), words["board_foot"], fill=MUTED, font=small)
    return _png(image.crop((0, 0, WIDTH, y + 90)))


def render_progress(step: int, language: str) -> bytes:
    """Where the person is: Sorted, Preparing, Your decision, Build (the current one lit)."""
    words = TEXT.get(language, TEXT["en"])
    image = Image.new("RGB", (WIDTH, 420), PAPER)
    draw = ImageDraw.Draw(image)
    draw.text((MARGIN, 48), "pi", fill=ACCENT, font=_font(46))
    draw.text((MARGIN, 112), words["progress"], fill=INK, font=_font(54))
    steps = words["steps"]
    inset = MARGIN + 100  # room for the first and last label to sit under their dot
    gap = (WIDTH - 2 * inset) // (len(steps) - 1) if len(steps) > 1 else 0
    for n, name in enumerate(steps):
        x = inset + n * gap
        colour = DONE if n < step else ACCENT if n == step else (214, 207, 198)
        if n:
            draw.line((x - gap + 28, 262, x - 28, 262), fill=colour, width=6)
        draw.ellipse((x - 26, 236, x + 26, 288), fill=colour)
        label = name[:16]
        draw.text(
            (x - draw.textlength(label, font=_font(26)) / 2, 306), label, fill=INK, font=_font(26)
        )
    draw.text((MARGIN, 366), words["progress_foot"], fill=MUTED, font=_font(26))
    return _png(image)
