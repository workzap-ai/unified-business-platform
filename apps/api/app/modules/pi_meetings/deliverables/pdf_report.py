"""The meeting summary as a designed PDF (A4, one or two pages for a normal meeting).

Drawn with ReportLab, which is pure Python (no system libraries). Latin text (English, Roman Urdu)
uses Helvetica. Urdu, Arabic and Persian lines use the Noto Naskh font the problem-map picture
already bundles (`app/modules/pi/fonts`): each such line is shaped with `arabic_reshaper`, put in
visual order with `python-bidi`, split into runs by script (the Naskh font has no Latin letters) and
drawn right-aligned. If the shaping packages or the font are missing, an Urdu line is drawn as
"(text not shown in this copy)" rather than as broken boxes: a wrong line would be worse than none.

Branding is Workzap only. The footer says the document was prepared by pi, an AI assistant, from
what the team approved.
"""

import io
from collections.abc import Callable
from pathlib import Path
from typing import Any

from reportlab.lib.colors import Color, HexColor  # type: ignore[import-untyped]
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.pdfbase.ttfonts import TTFont  # type: ignore[import-untyped]
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

from app.modules.pi_meetings.deliverables.content import ARABIC, Content, Line, is_rtl

BRAND = HexColor("#0D5E4F")
BRAND_SOFT = HexColor("#E3F2EE")
INK = HexColor("#1A1A1F")
MUTED = HexColor("#6B7078")
RULE = HexColor("#D9DEDC")
PAGE_W, PAGE_H = A4
MARGIN = 48.0
RIGHT = PAGE_W - MARGIN
BODY_W = PAGE_W - 2 * MARGIN
BOTTOM = 70.0
FONT_DIR = Path(__file__).resolve().parents[2] / "pi" / "fonts"
NASKH = "NotoNaskh"
NASKH_BOLD = "NotoNaskh-Bold"
HIDDEN = "(text not shown in this copy)"

_registered: bool | None = None


def _naskh_ready() -> bool:
    """Register the Urdu font once; False (and Urdu lines hidden) if it cannot be loaded."""
    global _registered
    if _registered is None:
        try:
            pdfmetrics.registerFont(TTFont(NASKH, str(FONT_DIR / "NotoNaskhArabic-Regular.ttf")))
            pdfmetrics.registerFont(TTFont(NASKH_BOLD, str(FONT_DIR / "NotoNaskhArabic-Bold.ttf")))
            _registered = True
        except Exception:  # a missing or unreadable font file
            _registered = False
    return _registered


def _rtl_tools() -> tuple[Callable[[str], str], Callable[..., str]] | None:
    try:
        import arabic_reshaper  # type: ignore[import-untyped]
        from bidi.algorithm import get_display  # type: ignore[import-untyped]
    except ImportError:
        return None
    return arabic_reshaper.reshape, get_display


NASKH_SCALE = 1.12  # Naskh looks smaller than Helvetica at the same size


def _visual(text: str, rtl: bool = True) -> str | None:
    """The line as it is drawn left to right (shaped, then reordered), or None if it cannot be.
    `rtl` is the line's main direction: Urdu text with a few English words is right-to-left, an
    English line with one Urdu word is left-to-right."""
    tools = _rtl_tools()
    if tools is None or not _naskh_ready():
        return None
    reshape, display = tools
    return str(display(reshape(text), base_dir="R" if rtl else "L"))


def _runs(visual: str, bold: bool) -> list[tuple[str, str]]:
    """Split a visual-order string into (text, font) runs: Naskh for Arabic-script letters,
    Helvetica for the rest. Spaces and punctuation stay with the run before them."""
    naskh = NASKH_BOLD if bold else NASKH
    latin = "Helvetica-Bold" if bold else "Helvetica"
    out: list[tuple[str, str]] = []
    for ch in visual:
        if ARABIC.match(ch):
            font = naskh
        elif ch.isalnum():
            font = latin
        else:
            font = out[-1][1] if out else naskh
        if out and out[-1][1] == font:
            out[-1] = (out[-1][0] + ch, font)
        else:
            out.append((ch, font))
    return out


def _size(font: str, size: float) -> float:
    return size * NASKH_SCALE if font.startswith("NotoNaskh") else size


def _width(visual: str, size: float, bold: bool) -> float:
    return float(sum(pdfmetrics.stringWidth(t, f, _size(f, size)) for t, f in _runs(visual, bold)))


class _Page:
    """A tiny layout cursor over one ReportLab canvas."""

    def __init__(self, buf: io.BytesIO, content: Content) -> None:
        self.c = canvas.Canvas(buf, pagesize=A4, pageCompression=1)
        self.c.setTitle(content.title)
        self.c.setAuthor("Workzap")
        self.c.setSubject("Meeting summary")
        self.content = content
        self.number = 0
        self.y = PAGE_H - MARGIN
        self.hidden = 0
        self._new_page()

    def _new_page(self) -> None:
        if self.number:
            self._footer()
            self.c.showPage()
        self.number += 1
        self.y = PAGE_H - MARGIN
        if self.number == 1:
            self._header()

    def _footer(self) -> None:
        c = self.c
        c.setStrokeColor(RULE)
        c.line(MARGIN, 52, RIGHT, 52)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 7.5)
        c.drawString(
            MARGIN,
            40,
            "Prepared by pi, Workzap's AI assistant, from what the team reviewed and approved.",
        )
        c.drawRightString(RIGHT, 40, f"Page {self.number}")

    def _header(self) -> None:
        c, content = self.c, self.content
        c.setFillColor(BRAND)
        c.rect(0, PAGE_H - 78, PAGE_W, 78, stroke=0, fill=1)
        c.setFillColor(Color(1, 1, 1))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(MARGIN, PAGE_H - 30, "Workzap")
        c.setFont("Helvetica", 8.5)
        c.drawString(MARGIN, PAGE_H - 44, "Meeting summary")
        self.y = PAGE_H - 78 - 30
        self.text(content.title, size=19, bold=True, color=INK, gap=6)
        if content.when:
            self.text(content.when, size=10, color=MUTED, gap=10)
        if content.people:
            roles = {"customer": "customer", "staff": "Workzap", "other": "", "unknown": ""}
            who = ", ".join(
                f"{label} ({roles[role]})" if roles.get(role) else label
                for label, role in content.people
            )
            self.text("In the meeting: " + who, size=9.5, color=MUTED, gap=14)

    def need(self, height: float) -> None:
        if self.y - height < BOTTOM:
            self._new_page()

    def text(
        self,
        words: str,
        *,
        size: float = 10.5,
        bold: bool = False,
        color: Color = INK,
        gap: float = 4,
        indent: float = 0,
        leading: float | None = None,
    ) -> None:
        """One paragraph, wrapped to the page. Right-to-left lines are right-aligned."""
        leading = leading or size * 1.45
        for line in self._wrap(words, size, bold, BODY_W - indent):
            self.need(leading)
            self.y -= leading
            self._draw(line, size, bold, color, indent)
        self.y -= gap

    def _wrap(self, words: str, size: float, bold: bool, width: float) -> list[str]:
        if ARABIC.search(words):
            return self._wrap_with(words, width, lambda s: self._measure_rtl(s, size, bold))
        font = "Helvetica-Bold" if bold else "Helvetica"
        return self._wrap_with(words, width, lambda s: pdfmetrics.stringWidth(s, font, size))

    def _measure_rtl(self, text: str, size: float, bold: bool) -> float:
        visual = _visual(text, is_rtl(text))
        return _width(visual, size, bold) if visual is not None else 0.0

    @staticmethod
    def _wrap_with(words: str, width: float, measure: Callable[[str], float]) -> list[str]:
        lines: list[str] = []
        current = ""
        for word in words.split():
            trial = f"{current} {word}".strip()
            if current and measure(trial) > width:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        return lines or [""]

    def _draw(self, line: str, size: float, bold: bool, color: Color, indent: float) -> None:
        c = self.c
        c.setFillColor(color)
        if ARABIC.search(line):
            rtl = is_rtl(line)
            visual = _visual(line, rtl)
            if visual is None:
                self.hidden += 1
                c.setFont("Helvetica-Oblique", size)
                c.drawString(MARGIN + indent, self.y, HIDDEN)
                return
            x = RIGHT - _width(visual, size, bold) if rtl else MARGIN + indent
            for part, font in _runs(visual, bold):
                c.setFont(font, _size(font, size))
                c.drawString(x, self.y, part)
                x += pdfmetrics.stringWidth(part, font, _size(font, size))
            return
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(MARGIN + indent, self.y, line)

    def heading(self, words: str) -> None:
        self.need(70)
        top = self.y - 12
        self.c.setFillColor(BRAND_SOFT)
        self.c.rect(MARGIN, top - 22, BODY_W, 22, stroke=0, fill=1)
        self.c.setFillColor(BRAND)
        self.c.setFont("Helvetica-Bold", 11)
        self.c.drawString(MARGIN + 8, top - 15, words)
        self.y = top - 22 - 6

    def bullet(self, line: Line) -> None:
        rtl = is_rtl(line.text)
        self.need(34)
        top = self.y
        self.text(line.text, size=10.5, indent=0 if rtl else 14, gap=1)
        if not rtl:
            self.c.setFillColor(BRAND)
            self.c.circle(MARGIN + 4, top - 11.4, 2, stroke=0, fill=1)
        notes = []
        if line.basis != "said in the meeting":
            notes.append(line.basis)
        if line.owner:
            notes.append(f"Owner: {line.owner}")
        if line.due:
            notes.append(f"Due: {line.due}")
        if notes:
            self.text("  |  ".join(notes), size=8, color=MUTED, indent=0 if rtl else 14, gap=5)
        else:
            self.y -= 4

    def finish(self) -> None:
        self._footer()
        self.c.save()


def render(content: Content) -> tuple[bytes, int]:
    """(the PDF, how many lines could not be drawn in this copy)."""
    buf = io.BytesIO()
    page: Any = _Page(buf, content)
    if content.summary:
        page.heading("Summary")
        page.text(content.summary, size=11, gap=8)
    for heading, lines in content.sections:
        page.heading(heading)
        for line in lines:
            page.bullet(line)
    page.finish()
    return buf.getvalue(), page.hidden
