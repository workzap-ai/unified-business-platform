"""After a busy session goes quiet, pi sends one "here's where we got to" summary:
only with at least three changes, once per set of changes, sharing the cards' gap."""

from datetime import UTC, datetime, timedelta

import pytest
from test_pi_deals import _customer_in_chat
from test_pi_pipeline import pi_workspace

from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi.session_snapshot import snapshot
from app.modules.pi_customer import engine

pytestmark = pytest.mark.integration


async def test_a_busy_session_gets_one_snapshot(api, business_db, monkeypatch):
    monkeypatch.setattr(engine, "prayer_or_quiet", lambda *a, **k: False)
    pi = await pi_workspace(api, business_db, business_type="service_business")
    _, conversation = await _customer_in_chat(pi, hours_ago=1)
    now = datetime.now(UTC)
    at = (now - timedelta(minutes=50)).isoformat()
    row = await pi.db.get(PiConversation, conversation.id)
    row.service_brief = {
        **row.service_brief,
        "customer_events": [
            {"at": at, "kind": "problem.noted", "title": "Online shop"},
            {"at": at, "kind": "problem.noted", "title": "Stock app"},
            {
                "at": at,
                "kind": "link.found",
                "title": "Online shop + Stock app",
                "detail": "same stock",
            },
        ],
        "customer_issues": {
            "issues": [
                {
                    "title": "Stock app",
                    "stage": "need_answer",
                    "ball_with": "client",
                    "open_question": "How many staff will use it?",
                },
            ],
        },
    }
    await pi.db.commit()

    first = await snapshot(pi.ctx, conversation.id, now)
    assert first is not None
    again = await snapshot(pi.ctx, conversation.id, now + timedelta(hours=3))
    assert again is None  # nothing new since the last snapshot
    message = await pi.db.get(PiMessage, first)
    assert message.body.startswith("Here's where we got to today:")
    assert "Online shop, Stock app" in message.body and "same stock" in message.body
    assert "How many staff will use it?" in message.body
    await pi.close()


async def test_too_little_happened_for_a_snapshot(api, business_db, monkeypatch):
    monkeypatch.setattr(engine, "prayer_or_quiet", lambda *a, **k: False)
    pi = await pi_workspace(api, business_db, business_type="service_business")
    _, conversation = await _customer_in_chat(pi, hours_ago=1)
    now = datetime.now(UTC)
    row = await pi.db.get(PiConversation, conversation.id)
    row.service_brief = {
        **row.service_brief,
        "customer_events": [
            {
                "at": (now - timedelta(minutes=40)).isoformat(),
                "kind": "problem.noted",
                "title": "Logo",
            },
        ],
    }
    await pi.db.commit()
    assert await snapshot(pi.ctx, conversation.id, now) is None
    await pi.close()
