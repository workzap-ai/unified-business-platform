"""The designed meeting documents: built only from approved insights, never a price or a phone
number, owner and deadline only when stated, a real PDF and a real PPTX, Urdu drawn not boxed."""

import io
import re
from datetime import UTC, datetime
from types import SimpleNamespace

from pptx import Presentation
from pypdf import PdfReader

from app.modules.pi_meetings.deliverables import content as c
from app.modules.pi_meetings.deliverables import deck, pdf_report


def row(kind, text, *, basis="stated", status="approved", owner="", due="", edited="", refs=(0,)):
    return SimpleNamespace(
        kind=kind,
        basis=basis,
        text=text,
        edited_text=edited,
        review_status=status,
        owner_label=owner,
        due_text=due,
        segment_refs=list(refs),
    )


WHEN = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)
PEOPLE = [("Ayesha", "customer"), ("Bilal", "staff")]


def made(*insights, title="Stock call with Ayesha"):
    return c.build(
        title=title, held_at=WHEN, created_at=None, participants=PEOPLE, insights=list(insights)
    )


def test_only_approved_or_edited_insights_are_used():
    out = made(
        row("summary", "They sell tiles and the stock runs out weekly."),
        row("problem", "Evening stock runs out", status="pending"),
        row("problem", "Staff forget to count", status="rejected"),
        row("decision", "Send a stock list", status="edited", edited="Send a stock list by Friday"),
    )
    texts = [ln.text for _, lines in out.sections for ln in lines]
    assert out.summary.startswith("They sell tiles")
    assert texts == ["Send a stock list by Friday"]
    assert out.used == 2 and out.dropped == 0


def test_a_line_with_a_price_is_left_out_and_counted():
    out = made(
        row("summary", "They want it."),
        row("action", "Quote Rs 50,000 for the system"),
        row("decision", "Budget is 2 lakh"),
        row("problem", "Stock runs out"),
    )
    shown = " ".join(ln.text for _, lines in out.sections for ln in lines)
    assert "50,000" not in shown and "lakh" not in shown and "Stock runs out" in shown
    assert out.dropped == 2


def test_phone_and_card_numbers_are_taken_out():
    out = made(row("summary", "Call Ayesha on 0300 1234567 or card 4111 1111 1111 1111 please."))
    assert "1234567" not in out.summary and "4111" not in out.summary


def test_owner_and_due_appear_only_when_stated():
    out = made(
        row("action", "Send the list", owner="Bilal", due="Friday"),
        row("next_step", "Review next week", basis="inferred"),
    )
    lines = dict(out.sections)["Actions and next steps"]
    assert (lines[0].owner, lines[0].due, lines[0].basis) == (
        "Bilal",
        "Friday",
        "said in the meeting",
    )
    assert (lines[1].owner, lines[1].due, lines[1].basis) == ("", "", "pi's reading")


def test_an_urdu_meeting_is_marked_right_to_left():
    out = made(row("summary", "ان کا اسٹاک ہر ہفتے ختم ہو جاتا ہے"), row("problem", "اسٹاک کم ہے"))
    assert out.language == "ur"
    assert made(row("summary", "Roman Urdu: stock har hafte khatam")).language == "en"


def test_the_pdf_is_a_real_pdf_with_the_words_in_it():
    out = made(
        row("summary", "They sell tiles and the stock runs out every week."),
        row("problem", "Evening stock runs out"),
        row("action", "Send the list", owner="Bilal", due="Friday"),
    )
    data, hidden = pdf_report.render(out)
    reader = PdfReader(io.BytesIO(data))
    text = " ".join(page.extract_text() for page in reader.pages)
    assert data.startswith(b"%PDF") and hidden == 0
    assert "Meeting summary" in text and "Stock call with Ayesha" in text
    assert "Evening stock runs out" in text and "Owner: Bilal" in text
    assert "Prepared by pi, Workzap's AI assistant" in text


def test_a_long_meeting_continues_on_a_second_page():
    many = [row("problem", f"Problem number {i} " + "word " * 25) for i in range(12)]
    many += [row("decision", f"Decision {i} " + "word " * 25) for i in range(12)]
    data, _ = pdf_report.render(made(row("summary", "Long."), *many))
    assert len(PdfReader(io.BytesIO(data)).pages) >= 2


def test_an_urdu_pdf_draws_the_letters_without_boxes():
    out = made(
        row("summary", "ان کا اسٹاک ہر ہفتے ختم ہو جاتا ہے۔"),
        row("problem", "شام کا اسٹاک کم پڑ جاتا ہے"),
        row("action", "فہرست جمعہ تک بھیجیں", owner="Bilal", due="Friday"),
    )
    data, hidden = pdf_report.render(out)
    assert data.startswith(b"%PDF") and hidden == 0
    fonts = {f for page in PdfReader(io.BytesIO(data)).pages for f in page["/Resources"]["/Font"]}
    assert fonts and any(
        "Naskh" in str(PdfReader(io.BytesIO(data)).pages[0]["/Resources"]["/Font"][f])
        for f in fonts
    )


def test_the_deck_is_an_editable_pptx_with_a_slide_per_section():
    out = made(
        row("summary", "They sell tiles."),
        row("problem", "Evening stock runs out"),
        row("decision", "Send a stock list"),
        row("action", "Send the list", owner="Bilal", due="Friday"),
        row("question", "Who counts stock?"),
    )
    prs = Presentation(io.BytesIO(deck.render(out)))
    titles = []
    for slide in prs.slides:
        words = " ".join(s.text_frame.text for s in slide.shapes if s.has_text_frame)
        titles.append(words)
    joined = " | ".join(titles)
    assert len(prs.slides) == 6  # title, summary, problems, decisions, actions, open
    assert "Stock call with Ayesha" in joined and "Evening stock runs out" in joined
    table = next(s for s in prs.slides[4].shapes if s.has_table).table
    assert [cell.text for cell in table.rows[1].cells] == ["Send the list", "Bilal", "Friday"]
    assert not re.search(r"\d{4}", joined.replace("2026", ""))


def test_a_long_section_continues_on_another_slide():
    many = [row("problem", f"Problem {i}") for i in range(8)]
    prs = Presentation(io.BytesIO(deck.render(made(row("summary", "S."), *many))))
    assert len(prs.slides) == 4  # title, summary, problems (1), problems (2)
