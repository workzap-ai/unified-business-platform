"""The meeting as an editable PowerPoint deck (16:9, python-pptx).

One title slide, the summary, then one slide per section (problems, needs, decisions, actions,
open questions), with an actions table showing owner and deadline when they were stated. Long
sections continue on a second slide. It is built from the same `Content` as the PDF, so it carries
exactly what the team approved and nothing a price, a card number or a phone number could be in.

Text is real, editable PowerPoint text (not pictures). Urdu, Arabic and Persian paragraphs are set
right-to-left with a complex-script font; PowerPoint shapes the letters itself, so the deck needs
no shaping done here. Branding is Workzap only.
"""

import io
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

from app.modules.pi_meetings.deliverables.content import Content, Line, is_rtl

BRAND = RGBColor(0x0D, 0x5E, 0x4F)  # type: ignore[no-untyped-call]
BRAND_SOFT = RGBColor(0xE3, 0xF2, 0xEE)  # type: ignore[no-untyped-call]
INK = RGBColor(0x1A, 0x1A, 0x1F)  # type: ignore[no-untyped-call]
MUTED = RGBColor(0x6B, 0x70, 0x78)  # type: ignore[no-untyped-call]
WHITE = RGBColor(0xFF, 0xFF, 0xFF)  # type: ignore[no-untyped-call]
FONT = "Calibri"
RTL_FONT = "Arial"  # PowerPoint shapes Urdu and Arabic with the system's complex-script face
PER_SLIDE = 5
SLIDE_W, SLIDE_H = Inches(13.333), Inches(7.5)
FOOTER = "Prepared by pi, Workzap's AI assistant, from what the team reviewed and approved."


def _style(run: Any, size: int, color: Any, bold: bool = False, rtl: bool = False) -> None:
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = FONT
    if rtl:
        rpr = run._r.get_or_add_rPr()
        for tag in ("cs",):
            node = rpr.makeelement(
                f"{{http://schemas.openxmlformats.org/drawingml/2006/main}}{tag}", {}
            )
            node.set("typeface", RTL_FONT)
            rpr.append(node)


def _para(
    frame: Any,
    words: str,
    size: int,
    color: Any = INK,
    bold: bool = False,
    first: bool = False,
) -> Any:
    p = frame.paragraphs[0] if first else frame.add_paragraph()
    rtl = is_rtl(words)
    if rtl:
        p._p.get_or_add_pPr().set("rtl", "1")
        p.alignment = PP_ALIGN.RIGHT
    run = p.add_run()
    run.text = words
    _style(run, size, color, bold, rtl)
    return p


def _box(slide: Any, x: Any, y: Any, w: Any, h: Any, fill: Any = None) -> Any:
    shape = slide.shapes.add_shape(1, x, y, w, h)  # a rectangle
    shape.line.fill.background()
    if fill is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    shape.shadow.inherit = False
    return shape


def _text(slide: Any, x: Any, y: Any, w: Any, h: Any) -> Any:
    box = slide.shapes.add_textbox(x, y, w, h)
    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = MSO_ANCHOR.TOP
    return frame


def _frame(prs: Any, heading: str, number: int) -> Any:
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    _box(slide, 0, 0, SLIDE_W, Inches(1.05), BRAND)
    title = _text(slide, Inches(0.6), Inches(0.2), Inches(11.6), Inches(0.7))
    _para(title, heading, 28, WHITE, True, first=True)
    mark = _text(slide, Inches(11.3), Inches(0.32), Inches(1.5), Inches(0.5))
    _para(mark, "Workzap", 14, WHITE, True, first=True).alignment = PP_ALIGN.RIGHT
    foot = _text(slide, Inches(0.6), Inches(7.0), Inches(11.0), Inches(0.35))
    _para(foot, FOOTER, 9, MUTED, first=True)
    num = _text(slide, Inches(12.0), Inches(7.0), Inches(0.8), Inches(0.35))
    _para(num, str(number), 9, MUTED, first=True).alignment = PP_ALIGN.RIGHT
    return slide


def _title_slide(prs: Any, content: Content) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _box(slide, 0, 0, SLIDE_W, SLIDE_H, BRAND)
    small = _text(slide, Inches(0.9), Inches(0.7), Inches(6), Inches(0.5))
    _para(small, "Workzap  |  Meeting summary", 14, WHITE, True, first=True)
    head = _text(slide, Inches(0.9), Inches(2.6), Inches(11.5), Inches(2.0))
    _para(head, content.title, 40, WHITE, True, first=True)
    if content.when:
        _para(head, content.when, 18, BRAND_SOFT)
    foot = _text(slide, Inches(0.9), Inches(6.7), Inches(11.5), Inches(0.5))
    _para(foot, FOOTER, 10, BRAND_SOFT, first=True)


def _bullets(slide: Any, lines: list[Line]) -> None:
    frame = _text(slide, Inches(0.7), Inches(1.45), Inches(11.9), Inches(5.3))
    for index, line in enumerate(lines):
        _para(frame, line.text, 20, first=index == 0).space_after = Pt(4)
        notes = []
        if line.basis != "said in the meeting":
            notes.append(line.basis)
        if line.owner:
            notes.append(f"Owner: {line.owner}")
        if line.due:
            notes.append(f"Due: {line.due}")
        if notes:
            _para(frame, "  |  ".join(notes), 12, MUTED).space_after = Pt(10)
        else:
            frame.paragraphs[-1].space_after = Pt(14)


def _actions(slide: Any, lines: list[Line]) -> None:
    rows = len(lines) + 1
    shape = slide.shapes.add_table(
        rows, 3, Inches(0.7), Inches(1.45), Inches(11.9), Emu(400000 * rows)
    )
    table = shape.table
    for col, width in enumerate((7.2, 2.4, 2.3)):
        table.columns[col].width = Inches(width)
    for col, label in enumerate(("Action", "Owner", "Due")):
        cell = table.cell(0, col)
        cell.fill.solid()
        cell.fill.fore_color.rgb = BRAND
        cell.text_frame.paragraphs[0].text = ""
        _para(cell.text_frame, label, 14, WHITE, True, first=True)
    for row, line in enumerate(lines, start=1):
        for col, value in enumerate((line.text, line.owner or "-", line.due or "-")):
            cell = table.cell(row, col)
            cell.fill.solid()
            cell.fill.fore_color.rgb = BRAND_SOFT if row % 2 else WHITE
            _para(cell.text_frame, value, 14, first=True)


def render(content: Content) -> bytes:
    prs = Presentation()
    prs.slide_width, prs.slide_height = SLIDE_W, SLIDE_H
    prs.core_properties.title = content.title
    prs.core_properties.author = "Workzap"
    _title_slide(prs, content)
    number = 1
    if content.summary:
        number += 1
        slide = _frame(prs, "Summary", number)
        _para(
            _text(slide, Inches(0.7), Inches(1.5), Inches(11.9), Inches(5.0)),
            content.summary,
            22,
            first=True,
        )
    for heading, lines in content.sections:
        for start in range(0, len(lines), PER_SLIDE):
            chunk = lines[start : start + PER_SLIDE]
            number += 1
            more = "" if len(lines) <= PER_SLIDE else f" ({start // PER_SLIDE + 1})"
            slide = _frame(prs, heading + more, number)
            if heading.startswith("Actions"):
                _actions(slide, chunk)
            else:
                _bullets(slide, chunk)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
