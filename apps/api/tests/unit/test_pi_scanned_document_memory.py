"""A scanned PDF is read page by page and each page keeps its number; pages past the cap are said
to be unread, never silently dropped. No model: the vision manager is a stub."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.pi import document_texts, documents
from app.shared.errors import BusinessRuleViolation

PDF = b"%PDF-1.4 scanned"


class Vision:
    def __init__(self) -> None:
        self.calls = 0

    async def vision(self, scope, prompt, images, **kwargs):
        self.calls += 1
        return SimpleNamespace(text=f"words on picture {self.calls}")


def _scanned(monkeypatch, total):
    def no_text(raw):
        raise BusinessRuleViolation("FILE_UNREADABLE", "no text")

    monkeypatch.setattr(documents, "document_text", no_text)
    shown = min(total, documents.MAX_SCANNED_PAGES)
    monkeypatch.setattr(
        documents,
        "pdf_page_pictures",
        lambda raw: ([(n, b"img", "image/jpeg") for n in range(1, shown + 1)], total),
    )


@pytest.mark.asyncio
async def test_each_scanned_page_is_read_and_returned_with_its_number(monkeypatch):
    _scanned(monkeypatch, 2)
    out: dict = {}
    text = await documents.read_document(Vision(), None, PDF, "a.pdf", uuid4(), scanned_out=out)
    assert out["pages"] == [(1, "words on picture 1"), (2, "words on picture 2")]
    assert out["total"] == 2 and "Page 2:" in text and "not read" not in text


@pytest.mark.asyncio
async def test_a_long_scan_says_only_the_first_pages_were_read(monkeypatch):
    _scanned(monkeypatch, 9)
    out: dict = {}
    text = await documents.read_document(Vision(), None, PDF, "a.pdf", uuid4(), scanned_out=out)
    assert len(out["pages"]) == documents.MAX_SCANNED_PAGES and out["total"] == 9
    assert "Only the first 4 of 9 pages were read" in text


class Session:
    def __init__(self):
        self.added = []

    def begin_nested(self):
        outer = self

        class Ctx:
            async def __aenter__(self):
                return None

            async def __aexit__(self, *a):
                return False

        del outer
        return Ctx()

    async def scalars(self, stmt):
        return []

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_scanned_pages_are_stored_marked_redacted_and_the_gap_is_a_row():
    session = Session()
    scope = SimpleNamespace(tenant_id=uuid4(), environment_id=uuid4())
    pages = [(1, "Call 0311 2546598 about the order"), (2, "Total 500 due")]
    added = await document_texts.store_scanned(
        session, scope, customer_id=uuid4(), file_id=uuid4(), pages=pages, total=9
    )
    assert added == 3
    refs = [r.ref for r in session.added]
    assert refs == [
        "page 1 (read from a picture)",
        "page 2 (read from a picture)",
        "pages not read",
    ]
    assert all("2546598" not in r.text for r in session.added)
    assert "first 2 of 9" in session.added[2].text


@pytest.mark.asyncio
async def test_no_pages_stores_nothing():
    session = Session()
    scope = SimpleNamespace(tenant_id=uuid4(), environment_id=uuid4())
    assert (
        await document_texts.store_scanned(
            session, scope, customer_id=uuid4(), file_id=uuid4(), pages=[], total=5
        )
        == 0
    )
