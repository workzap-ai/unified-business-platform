"""pi reads more of what customers send: Excel and PowerPoint text locally, and a photo
sent as a file through the vision model (instead of handing the chat to a person)."""

import io
import zipfile
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.pi.documents import document_text, read_document
from app.shared.errors import BusinessRuleViolation

S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _zip(files: dict[str, str]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, body in files.items():
            archive.writestr(name, body)
    return out.getvalue()


def test_excel_rows_are_read():
    raw = _zip(
        {
            "xl/workbook.xml": f'<workbook xmlns="{S}"/>',
            "xl/sharedStrings.xml": f'<sst xmlns="{S}"><si><t>Item</t></si>'
            f"<si><t>Daily sales report</t></si></sst>",
            "xl/worksheets/sheet1.xml": f'<worksheet xmlns="{S}"><sheetData>'
            f'<row><c t="s"><v>0</v></c><c><v>Qty</v></c></row>'
            f'<row><c t="s"><v>1</v></c><c><v>25</v></c></row></sheetData></worksheet>',
        }
    )
    label, text = document_text(raw)
    assert label == "Excel sheet"
    assert "Item | Qty" in text and "Daily sales report | 25" in text


def test_powerpoint_slides_are_read():
    raw = _zip(
        {
            "ppt/presentation.xml": "<p/>",
            "ppt/slides/slide1.xml": f'<sld xmlns:a="{A}"><a:t>Project kickoff</a:t></sld>',
            "ppt/slides/slide2.xml": f'<sld xmlns:a="{A}"><a:t>Scope: ERP for sales</a:t></sld>',
        }
    )
    label, text = document_text(raw)
    assert label == "PowerPoint, 2 slides"
    assert "Slide 1: Project kickoff" in text and "Slide 2: Scope: ERP for sales" in text


async def test_a_photo_sent_as_a_file_goes_to_vision():
    seen = []

    async def vision(scope, prompt, images, **kwargs):
        seen.append(images[0][1])
        return SimpleNamespace(text="A handwritten list: logo, website, three pages.")

    manager = SimpleNamespace(vision=vision)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    text = await read_document(manager, None, png, "notes.png", uuid4())
    assert seen == ["image/png"]
    assert text.startswith("Document notes.png (picture): A handwritten list")


async def test_an_unknown_file_still_raises():
    manager = SimpleNamespace()
    with pytest.raises(BusinessRuleViolation):
        await read_document(manager, None, _zip({"random.txt": "x"}), "x.zip", uuid4())
