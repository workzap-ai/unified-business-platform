"""Pi (Agenta), the operator assistant: same scope as the console, no customer content,
figures only from facts, audited."""

import json
from uuid import UUID

import pytest
from pi_saas_support import FakeProvider, configure, pi_client, pi_register
from sqlalchemy import func, select
from test_service_lifecycle import register

from app.modules.audit.models import AuditEvent
from app.modules.pi_saas.agenta import figures_supported, topic_for
from app.modules.pi_saas.models import PiOperatorMember

pytestmark = pytest.mark.integration


def test_topics_and_figure_check():
    assert topic_for("Kis ki payment ruki hui hai?") == "billing"
    assert topic_for("Which businesses are stuck in setup?") == "setup"
    assert topic_for("koi masla hai webhooks mein?") == "health"
    assert topic_for("Good morning") == "summary"
    facts = {"businesses_visible": 3, "by_setup_state": {"live": 2, "draft": 1}}
    assert figures_supported("You have 3 businesses; 2 are live.", facts)
    assert not figures_supported("You have 7 businesses.", facts)


async def test_agenta_answers_within_the_operator_scope(api, business_db):
    app = api._transport.app  # type: ignore[attr-defined]
    configure(app, FakeProvider())
    client = pi_client(app)
    await pi_register(client, "Noor Tailors")
    identity = await register(api)
    ask = {"question": "Which businesses need attention?"}
    assert (await api.post("/api/v1/operator/pi/agenta/ask", json=ask)).status_code == 403

    # A support operator sees only assigned businesses: none yet.
    member = PiOperatorMember(user_id=UUID(identity["user"]["id"]), role="support")
    business_db.add(member)
    await business_db.flush()
    scoped = (await api.post("/api/v1/operator/pi/agenta/ask", json=ask)).json()
    assert scoped["facts"]["businesses_visible"] == 0
    assert "Noor Tailors" not in scoped["answer"]
    assert "workspaces" not in scoped["facts"] or scoped["facts"]["not_visible"]

    member.role = "owner"
    await business_db.flush()
    setup = (
        await api.post(
            "/api/v1/operator/pi/agenta/ask", json={"question": "Kaun setup mein atka hai?"}
        )
    ).json()
    assert setup["topic"] == "setup" and setup["generated_by"] == "template"
    assert any(b["name"] == "Noor Tailors" for b in setup["facts"]["businesses"])
    assert "Noor Tailors" in setup["answer"]
    assert setup["links"][0]["href"].startswith("/operator/")
    # Facts are operational only: no conversation or message content keys.
    blob = json.dumps(setup["facts"]).lower()
    assert "body" not in blob and "message_preview" not in blob
    audited = await business_db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.action == "pi_operator.agenta_asked")
    )
    assert audited == 2
    await client.aclose()
