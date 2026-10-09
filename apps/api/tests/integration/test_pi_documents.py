"""A customer sends a PDF on WhatsApp: pi reads it and answers about it, instead of
handing it to the team. A scanned PDF with no text still goes to a person."""

from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import mock_turns, turn
from test_pi_teach_files import make_docx, make_pdf

from app.ai.manager import LLMManager
from app.modules.pi.documents import document_text
from app.modules.pi.models import PiMessage
from app.shared.errors import BusinessRuleViolation

pytestmark = pytest.mark.integration


def test_document_text_reads_pdf_word_and_text():
    label, text = document_text(make_pdf(["Project proposal: AI dashboard for employees"]))
    assert label == "PDF, 1 page" and "AI dashboard" in text
    label, text = document_text(make_docx(["Scope: staff performance charts and alerts"]))
    assert label == "Word document" and "performance charts" in text
    assert document_text(b"Plain notes about the project scope.")[0] == "text file"
    with pytest.raises(BusinessRuleViolation):
        document_text(make_pdf([]))  # no text layer, like a scan


def _serve(pi, content: bytes, mime: str = "application/pdf") -> None:
    """The file download is faked; everything else (sending replies) uses the test's
    normal fake WhatsApp transport."""
    normal = pi.http._transport

    async def meta(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/555666777"):
            return httpx.Response(
                200,
                json={
                    "url": "https://lookaside.fbsbx.com/media/doc",
                    "mime_type": mime,
                    "file_size": len(content),
                },
            )
        if request.url.host == "lookaside.fbsbx.com":
            return httpx.Response(200, content=content)
        return await normal.handle_async_request(request)

    pi.http = httpx.AsyncClient(transport=httpx.MockTransport(meta))
    pi.ctx["http"] = pi.http


async def test_a_pdf_proposal_is_read_and_answered(api, business_db, monkeypatch):
    summaries = []

    async def complete(self, scope, **kwargs):
        summaries.append(kwargs["messages"][-1].text())
        return SimpleNamespace(
            text="Project proposal: an AI dashboard to visualise employee performance.\n"
            "• Charts per team • Weekly alerts • Budget 5,000 USD",
            attempts=[],
        )

    monkeypatch.setattr(LLMManager, "complete", complete)
    contexts = mock_turns(
        monkeypatch,
        turn(
            reply="Thanks, I'm pi, the company's AI assistant. I read your proposal: an AI "
            "dashboard for employee performance with team charts and weekly alerts. Who "
            "will use it day to day?",
            language="en",
        ),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    _serve(pi, make_pdf(["Project proposal: AI dashboard for employees", "Budget 5000 USD"]))
    await pi.process(
        "Here is my project proposal", "wamid.doc-1", kind="document", media_id="555666777"
    )
    await pi.deliver_all()

    assert "AI dashboard for employees" in summaries[0]  # the PDF's own text was read
    inbound = await business_db.scalar(
        select(PiMessage).where(PiMessage.provider_message_id == "wamid.doc-1")
    )
    assert "Document" in inbound.body and "AI dashboard" in inbound.body
    assert inbound.media["file_kind"] == "document"
    conversation = await pi.conversation()
    assert conversation.mode == "ai"  # no handoff
    assert "AI dashboard" in contexts[0]
    replies = [m.body for m in await pi.outbound()]
    assert any("I read your proposal" in r for r in replies)
    await pi.close()


async def test_a_scanned_pdf_still_goes_to_a_person(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    _serve(pi, make_pdf([]))
    await pi.process("", "wamid.doc-2", kind="document", media_id="555666777")
    assert (await pi.conversation()).mode == "human"
    await pi.close()


async def test_figures_from_the_document_can_be_repeated_but_not_its_prices(
    api, business_db, monkeypatch
):
    """The real case: a 26-page brief with 100,000 feeds, October 2026 and $1.30 per
    camera. The reply may repeat the customer's own counts and dates; the price sentence
    is dropped; the chat stays with pi."""

    async def complete(self, scope, **kwargs):
        return SimpleNamespace(
            text="Product brief: analytics for 100,000 camera feeds, live October 2026, "
            "budget $1.30 per camera.",
            attempts=[],
        )

    monkeypatch.setattr(LLMManager, "complete", complete)
    mock_turns(
        monkeypatch,
        turn(
            reply="Thanks, I'm pi, the company's AI assistant. I read your brief: analytics "
            "for 100,000 camera feeds, going live in October 2026. You mentioned $1.30 per "
            "camera. Which part should the team look at first?",
            language="en",
        ),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    _serve(pi, make_pdf(["Product brief DRAFT 2", "100,000 feeds", "October 2026"]))
    await pi.process("", "wamid.doc-3", kind="document", media_id="555666777")
    await pi.deliver_all()
    assert (await pi.conversation()).mode == "ai"
    [reply] = [m.body for m in await pi.outbound()]
    assert "100,000 camera feeds" in reply and "October 2026" in reply
    assert "$" not in reply and "1.30" not in reply
    await pi.close()
