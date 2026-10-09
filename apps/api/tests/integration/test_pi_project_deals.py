"""One deal per project: a chat with two confirmed projects gets two leads, each with
its own brief and its own proposal; an older lead of the chat is reused only by the
project with its name; won deals are never reopened."""

import json
from uuid import UUID

import pytest
from sqlalchemy import select
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import mock_turns, turn

from app.modules.pi.service_conversation import Project, Requirements
from app.modules.sales.models import SalesLead

pytestmark = pytest.mark.integration

WEBSITE = Project(
    title="Furniture website",
    service="Website",
    details="Categories, cart, payment gateway",
    status="confirmed",
)
AI = Project(
    title="AI system for employees",
    service="AI dashboard",
    details="Performance charts and weekly alerts",
    status="confirmed",
)


def _both(**changes):
    return turn(
        reply="Thanks, I'm pi, the company's AI assistant. Both are noted.",
        language="en",
        projects=[WEBSITE, AI],
        requirements=Requirements(service="Website", customer_budget="flexible"),
        missing=[],
        ready_for_team=True,
        awaiting_customer=False,
        **changes,
    )


async def _leads(pi) -> dict[str, SalesLead]:
    rows = await pi.db.scalars(select(SalesLead).where(SalesLead.tenant_id == UUID(pi.tenant_id)))
    return {row.title: row for row in rows}


def _record_proposals(monkeypatch) -> list[str]:
    """Lead ids pi queues a proposal for (the job itself is tested elsewhere)."""
    from app.modules.pi_saas import jobs

    queued: list[str] = []

    async def enqueue_proposal(ctx, lead_id):
        queued.append(str(lead_id))

    monkeypatch.setattr(jobs, "enqueue_proposal", enqueue_proposal)
    return queued


async def test_two_confirmed_projects_become_two_deals(api, business_db, monkeypatch):
    contexts = mock_turns(monkeypatch, _both(), _both())
    queued = _record_proposals(monkeypatch)
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("Furniture website and an AI system, yes both", "pd-1")
    await pi.deliver_all()
    leads = await _leads(pi)
    assert set(leads) == {"Furniture website", "AI system for employees"}
    website, ai = leads["Furniture website"], leads["AI system for employees"]
    assert website.stage == ai.stage == "qualified"
    assert website.requirements["scope"] == "Categories, cart, payment gateway"
    assert ai.requirements["scope"] == "Performance charts and weekly alerts"
    assert ai.requirements["service"] == "AI dashboard"
    # The turn's budget was about the website (the current service), not the AI system.
    assert website.requirements.get("customer_budget") == "flexible"
    assert "customer_budget" not in ai.requirements
    assert sorted(queued) == sorted([str(website.id), str(ai.id)])

    # Talking again doesn't open more leads or more proposals.
    await pi.process("thanks", "pd-2")
    await pi.deliver_all()
    assert set(await _leads(pi)) == {"Furniture website", "AI system for employees"}
    assert len(queued) == 2
    # pi now knows each project's real next step for its "what happens next" line.
    steps = {d["project"]: d["next"] for d in json.loads(contexts[1])["project_deals"]}
    assert set(steps) == {"Furniture website", "AI system for employees"}
    assert all("preparing the proposal" in step for step in steps.values())
    await pi.close()


async def test_a_project_still_being_discussed_waits(api, business_db, monkeypatch):
    collecting = Project(title="Logo", service="Logo design", status="collecting")
    mock_turns(
        monkeypatch,
        turn(
            reply="Thanks, I'm pi, the company's AI assistant.",
            projects=[WEBSITE, collecting],
            requirements=Requirements(service="Website"),
        ),
    )
    queued = _record_proposals(monkeypatch)
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("website yes, logo maybe", "pd-3")
    await pi.deliver_all()
    leads = await _leads(pi)
    assert leads["Furniture website"].stage == "qualified"
    assert leads["Logo"].stage == "new"
    assert queued == [str(leads["Furniture website"].id)]
    await pi.close()


async def test_an_older_lead_belongs_to_the_project_with_its_name(api, business_db, monkeypatch):
    mock_turns(
        monkeypatch,
        # Before: one lead per chat, named after the service.
        turn(
            reply="Thanks, I'm pi, the company's AI assistant.",
            requirements=Requirements(service="Furniture website"),
        ),
        _both(),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("furniture website", "pd-4")
    await pi.deliver_all()
    [old] = (await _leads(pi)).values()
    await pi.process("and an AI system too, confirmed", "pd-5")
    await pi.deliver_all()
    leads = await _leads(pi)
    assert leads["Furniture website"].id == old.id  # adopted, not duplicated
    assert "AI system for employees" in leads and len(leads) == 2
    await pi.close()


async def test_each_project_keeps_its_own_proposal_state(api, business_db, monkeypatch):
    """Making the first project's proposal must not mark the second one as done."""
    from app.modules.pi_saas.jobs import _mark_proposal, _proposal_state, _proposals_due

    mock_turns(monkeypatch, _both())
    _record_proposals(monkeypatch)
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("both confirmed", "pd-6")
    await pi.deliver_all()
    leads = await _leads(pi)
    website, ai = leads["Furniture website"], leads["AI system for employees"]
    assert await _proposal_state(pi.db, website) == "due"
    assert await _proposal_state(pi.db, ai) == "due"
    await _mark_proposal(pi.db, website, "made")
    await pi.db.commit()
    assert await _proposal_state(pi.db, website) == "made"
    assert await _proposal_state(pi.db, ai) == "due"
    # A lost job is retried for the lead still due only.
    from datetime import UTC, datetime, timedelta

    conversation = await pi.conversation()
    conversation.updated_at = datetime.now(UTC) - timedelta(minutes=5)
    await pi.db.commit()
    assert str(ai.id) in await _proposals_due(pi.db)
    assert str(website.id) not in await _proposals_due(pi.db)
    await pi.close()
