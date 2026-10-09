"""The customer's timeline (profile → Activity) follows the chat: each new request pi
picks up, its confirmation, and documents received. Never one entry per chat turn."""

from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_pi_documents import _serve
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import mock_turns, turn
from test_pi_teach_files import make_pdf

from app.ai.manager import LLMManager
from app.modules.customers.models import CustomerActivity
from app.modules.pi.service_conversation import Project, Requirements

pytestmark = pytest.mark.integration


async def _timeline(pi) -> list[str]:
    conversation = await pi.conversation()
    rows = await pi.db.scalars(
        select(CustomerActivity)
        .where(CustomerActivity.customer_id == conversation.customer_id)
        .order_by(CustomerActivity.created_at)
    )
    return [row.summary for row in rows]


def _asked(status: str, ready: bool = False):
    return turn(
        reply="Thanks, I'm pi, the company's AI assistant. Noted.",
        language="en",
        requirements=Requirements(service="Furniture e-commerce website"),
        projects=[
            Project(
                title="Furniture e-commerce website",
                details="Shop with cart and payments",
                status=status,
            )
        ],
        ready_for_team=ready,
        awaiting_customer=not ready,
    )


async def test_new_and_confirmed_requests_reach_the_timeline_once(api, business_db, monkeypatch):
    mock_turns(
        monkeypatch,
        _asked("collecting"),
        _asked("collecting"),
        _asked("confirmed", ready=True),
        _asked("confirmed", ready=True),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    for index, text in enumerate(
        ["I need a furniture shop website", "with cart", "yes that's all", "ok thanks"]
    ):
        await pi.process(text, f"act-{index}")
        await pi.deliver_all()
    timeline = await _timeline(pi)
    requests = [t for t in timeline if "Furniture e-commerce website" in t]
    assert requests == [
        "Requirement captured: Furniture e-commerce website",
        "Request confirmed: Furniture e-commerce website: Shop with cart and payments",
    ]
    await pi.close()


async def test_a_document_is_on_the_timeline(api, business_db, monkeypatch):
    async def complete(self, scope, **kwargs):
        return SimpleNamespace(text="Product brief: camera analytics.", attempts=[])

    monkeypatch.setattr(LLMManager, "complete", complete)
    mock_turns(monkeypatch, turn(reply="Thanks, I'm pi, the company's AI assistant. Read it."))
    pi = await pi_workspace(api, business_db, business_type="service_business")
    _serve(pi, make_pdf(["Product brief VISION", "Camera analytics"]))
    await pi.process("", "wamid.act-doc", kind="document", media_id="555666777")
    await pi.deliver_all()
    assert any(t.startswith("Document received on WhatsApp") for t in await _timeline(pi))
    await pi.close()


async def test_a_second_request_in_the_same_chat_is_added(api, business_db, monkeypatch):
    first = _asked("collecting")
    second = _asked("collecting")
    second.projects = [
        *first.projects,
        Project(title="AI system for employees", details="Dashboards", status="collecting"),
    ]
    mock_turns(monkeypatch, first, second)
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("I need a furniture shop website", "two-1")
    await pi.deliver_all()
    await pi.process("Also an AI system for my employees", "two-2")
    await pi.deliver_all()
    timeline = await _timeline(pi)
    assert "New request from WhatsApp: AI system for employees: Dashboards" in timeline
    await pi.close()
