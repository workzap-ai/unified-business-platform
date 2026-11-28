"""Draws one slide as a 1280 x 720 picture, for pi to show in a room (Pillow only).

The room agent publishes the picture as pi's video, so there is no browser or office program in
the loop: plain text on a clean page in Workzap's colours, large enough to read on a phone. Urdu,
Arabic and Persian lines are shaped and put in visual order (the same tools and the Noto Naskh
font the problem-map picture uses), so a slide in Urdu reads right to left with its bullet on the
right, and a line that mixes Urdu and English is drawn run by run in the right font. A slide never
draws outside its page: the text shrinks to fit and, if it still does not fit, the last bullets are
left off rather than running over the footer.
"""

from typing import Any

from PIL import Image, ImageDraw

from app.modules.pi import map_render as mr
from app.modules.pi_meetings.deliverables.content import ARABIC, is_rtl

WIDTH, HEIGHT = 1280, 720  # both even: the video track has the size of its first frame
BRAND = (13, 94, 79)
INK = (26, 26, 31)
MUTED = (107, 112, 120)
SOFT = (227, 242, 238)
WHITE = (255, 255, 255)
MARGIN = 80
HEADER_H = 120
BODY_TOP = 170
BODY_BOTTOM = 636
FOOTER_Y = 690
FOOTER = "Prepared by pi, Workzap's AI assistant."
BULLET_SIZES = (38, 34, 30, 27, 24)
LINE_GAP = 1.3  # line height as a multiple of the text size
BULLET_GAP = 0.55  # space between bullets as a multiple of the text size


def _arabic(text: str) -> bool:
    return any(ARABIC.match(c) for c in text)


def _pieces(text: str, size: int, bold: bool = False) -> tuple[list[tuple[str, Any]], float]:
    """The (text, font) runs in the order they are drawn, left to right, and their total width."""
    if _arabic(text):
        try:
            reshape, display = mr._load_rtl()
            visual = str(display(reshape(text), base_dir="R" if is_rtl(text) else "L"))
            runs = []
            total = 0.0
            for run, latin in mr._runs(visual):
                font = mr._font(size, bold, naskh=not latin)
                runs.append((run, font))
                total += float(font.getlength(run))
            return runs, total
        except (ImportError, OSError):  # no shaping tools or font: drawn plain, never a crash
            pass
    font = mr._font(size, bold)
    return [(text, font)], float(font.getlength(text))


def width_of(text: str, size: int, bold: bool = False) -> float:
    return _pieces(text, size, bold)[1]


def wrap(text: str, size: int, max_width: int, bold: bool = False) -> list[str]:
    """The text broken into lines that fit `max_width` (logical order, one word never split)."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and width_of(candidate, size, bold) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _line(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    left: int,
    right: int,
    baseline: int,
    size: int,
    fill: tuple[int, int, int],
    bold: bool = False,
    center: bool = False,
) -> None:
    runs, total = _pieces(text, size, bold)
    if center:
        x = (left + right - total) / 2
    elif _arabic(text) and is_rtl(text):
        x = right - total  # a right-to-left line starts at the right margin
    else:
        x = float(left)
    for run, font in runs:
        draw.text((x, baseline), run, font=font, fill=fill, anchor="ls")  # one baseline for all
        x += float(font.getlength(run))


def _fit_heading(heading: str, size: int, max_width: int) -> int:
    while size > 28 and width_of(heading, size, True) > max_width:
        size -= 2
    return size


def _bullets(bullets: list[str]) -> tuple[int, list[list[str]]]:
    """The largest text size at which the bullets fit the page, and each bullet's lines. Bullets
    that still do not fit at the smallest size are dropped from the end."""
    shown = list(bullets)
    while True:
        for size in BULLET_SIZES:
            wrapped = [wrap(b, size, WIDTH - 2 * MARGIN - 40) for b in shown]
            lines = sum(len(w) for w in wrapped)
            height = lines * size * LINE_GAP + max(0, len(wrapped) - 1) * size * BULLET_GAP
            if BODY_TOP + height <= BODY_BOTTOM:
                return size, wrapped
        if len(shown) <= 1:
            return BULLET_SIZES[-1], [
                wrap(b, BULLET_SIZES[-1], WIDTH - 2 * MARGIN - 40) for b in shown
            ]
        shown.pop()


def render(slide: dict[str, Any], number: int, total: int) -> Image.Image:
    """The picture of slide `number` of `total`."""
    image = Image.new("RGB", (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(image)
    heading = str(slide.get("heading") or "")
    bullets = [str(b) for b in slide.get("bullets") or [] if str(b).strip()]
    title_page = slide.get("kind") == "title"
    if title_page:
        draw.rectangle((0, 0, WIDTH, 24), fill=BRAND)
        draw.rectangle((MARGIN, 300, MARGIN + 120, 308), fill=BRAND)
        size = _fit_heading(heading, 72, WIDTH - 2 * MARGIN)
        _line(
            draw,
            heading,
            left=MARGIN,
            right=WIDTH - MARGIN,
            baseline=290,
            size=size,
            fill=INK,
            bold=True,
            center=True,
        )
        for i, text in enumerate(bullets[:2]):
            _line(
                draw,
                text,
                left=MARGIN,
                right=WIDTH - MARGIN,
                baseline=400 + i * 56,
                size=34,
                fill=MUTED,
                center=True,
            )
    else:
        draw.rectangle((0, 0, WIDTH, HEADER_H), fill=BRAND)
        size = _fit_heading(heading, 46, WIDTH - 2 * MARGIN - 220)
        _line(
            draw,
            heading,
            left=MARGIN,
            right=WIDTH - MARGIN - 220,
            baseline=HEADER_H // 2 + 16,
            size=size,
            fill=WHITE,
            bold=True,
        )
        _line(
            draw,
            "Workzap",
            left=WIDTH - MARGIN - 200,
            right=WIDTH - MARGIN,
            baseline=HEADER_H // 2 + 10,
            size=26,
            fill=WHITE,
            center=True,
        )
        text_size, wrapped = _bullets(bullets)
        y = float(BODY_TOP)
        for lines in wrapped:
            rtl = _arabic(lines[0]) and is_rtl(" ".join(lines))
            dot_x = WIDTH - MARGIN - 8 if rtl else MARGIN + 8
            draw.ellipse(
                (dot_x - 7, y + text_size * 0.62 - 7, dot_x + 7, y + text_size * 0.62 + 7),
                fill=BRAND,
            )
            for text in lines:
                y += text_size * LINE_GAP
                _line(
                    draw,
                    text,
                    left=MARGIN + 40,
                    right=WIDTH - MARGIN - 40,
                    baseline=int(y - text_size * 0.3),
                    size=text_size,
                    fill=INK,
                )
            y += text_size * BULLET_GAP
    draw.rectangle((0, FOOTER_Y - 34, WIDTH, FOOTER_Y - 33), fill=SOFT)
    _line(draw, FOOTER, left=MARGIN, right=WIDTH // 2, baseline=FOOTER_Y, size=20, fill=MUTED)
    _line(
        draw,
        f"{number} / {total}",
        left=WIDTH - MARGIN - 160,
        right=WIDTH - MARGIN,
        baseline=FOOTER_Y,
        size=20,
        fill=MUTED,
        center=True,
    )
    return image
