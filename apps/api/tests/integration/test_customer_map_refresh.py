"""An out-of-date Problem Map (saved under older analysis rules, here with the
customer's ERP request wrongly dropped) is made again when the team opens the customer,
without waiting for the customer's next message."""

from types import SimpleNamespace
from uuid import UUID

import pytest
from test_pi_deals import _customer_in_chat
from test_pi_pipeline import pi_workspace

from app.ai.manager import LLMManager
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi_customer.service import Issue, IssueReport

pytestmark = pytest.mark.integration


async def test_an_old_map_is_rebuilt_when_the_team_opens_the_customer(
    api, business_db, monkeypatch
):
    calls: list[str] = []

    async def complete(self, scope, output, **kwargs):
        calls.append(kwargs.get("purpose", ""))
        report = IssueReport(
            headline="The team is preparing your ERP proposal",
            issues=[Issue(title="ERP System Requirements", category="inquiry", stage="on_it")],
        )
        return SimpleNamespace(value=report, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)
    pi = await pi_workspace(api, business_db, business_type="service_business")
    customer_id, conversation = await _customer_in_chat(pi)
    pi.db.add(
        PiMessage(
            tenant_id=UUID(pi.tenant_id),
            environment_id=UUID(pi.environment_id),
            conversation_id=conversation.id,
            direction="inbound",
            sender_type="customer",
            message_type="text",
            body="I need an ERP for daily reporting and my sales team",
            status="processed",
        )
    )
    row = await pi.db.get(PiConversation, conversation.id)
    row.service_brief = {
        **(row.service_brief or {}),
        "customer_issues": {  # saved before the fix: no version, the request dropped
            "at": row.last_message_at.isoformat(),
            "issues": [],
            "links": [],
            "service_issues": [{"title": "ERP System Requirements"}],
        },
    }
    await pi.db.commit()

    first = (await api.get(f"/api/v1/customers/{customer_id}/pi-overview")).json()
    # pi's analysis first, then the brief's other projects (Logo, Website).
    assert [i["title"] for i in first["issues"]] == ["ERP System Requirements", "Logo", "Website"]
    assert calls == ["pi_customer_issues"]
    # Up to date now: opening the customer again makes no AI call.
    await api.get(f"/api/v1/customers/{customer_id}/pi-overview")
    assert calls == ["pi_customer_issues"]
    await pi.close()


def test_projects_from_the_brief_join_the_map_without_duplicates():
    from app.modules.pi_saas.customer_overview import brief_projects

    conversation = SimpleNamespace(
        id="c1",
        service_brief={
            "projects": [
                {"title": "Furniture E-commerce Website", "status": "collecting"},
                {"title": "Map Inquiry", "status": "collecting"},
                {"title": "AI System for Visualization", "status": "confirmed"},
                {"title": "Video Project: The Pulse of Precision", "status": "collecting"},
            ]
        },
    )
    analysed = [{"title": "Video Editing Request"}, {"title": "Additional Platform Request"}]
    added = brief_projects(conversation, analysed)
    assert [(p["title"], p["stage"], p["ball_with"]) for p in added] == [
        ("Furniture E-commerce Website", "noted", "pi"),
        ("AI System for Visualization", "on_it", "team"),
    ]
    assert added[1]["next_step"] == "Team: prepare the proposal"
