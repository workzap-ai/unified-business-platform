"""Brain mode never opens a lead, a project or a team brief on its own (R-SELL-02)."""

import pytest
from sqlalchemy import func, select
from test_pi_brain_problems import adaptive, say, workspace
from test_pi_service_conversations import turn

from app.modules.pi.models import PiConversation
from app.modules.sales.models import SalesLead

pytestmark = pytest.mark.integration


def eager(context, n):
    """A model that still follows the older flow: it marks the brief ready and opens a project."""
    from app.modules.pi.service_conversation import Project

    return turn(
        reply="Noted: a cattle farm dashboard. Which part is the biggest problem right now?",
        language="en",
        ready_for_team=True,
        awaiting_customer=False,
        projects=[Project(title="Cattle Farm Management System", status="confirmed")],
    )


async def test_the_older_team_handoff_does_not_run_in_brain_mode(api, business_db, monkeypatch):
    adaptive(monkeypatch, eager)
    pi = await workspace(api, business_db)
    await say(pi, "I want a dashboard for my cattle farm with workers and cameras", "bi-1")
    conversation = (await business_db.scalars(select(PiConversation))).one()
    brief = conversation.service_brief or {}
    assert not brief.get("ready_for_team") and not brief.get("projects")
    assert await business_db.scalar(select(func.count()).select_from(SalesLead)) == 0
    await pi.close()
