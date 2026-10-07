# ruff: noqa: F811 - pytest fixtures imported from the portal tests
"""pi Customer v2 engine: links between requests, the activity timeline, visual cards
and the follow-up ladder (customer's turn and team's turn)."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pi_saas_support import pi_client, worker_ctx
from sqlalchemy import select
from test_pi_customer_portal import (  # noqa: F401 - fixtures
    CSRF_COOKIE,
    PORTAL,
    _business_with_chat,
    _sign_in,
    app,
    provider,
)

from app.ai.manager import LLMManager
from app.modules.notifications.models import Notification
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi_customer import engine
from app.modules.pi_customer.cards import card_token, read_card
from app.modules.pi_customer.service import Issue, IssueLink, IssueReport

pytestmark = pytest.mark.integration

LINKED = IssueReport(
    headline="Kitne staff ERP app use karenge?",
    issues=[
        Issue(
            title="Furniture website",
            stage="on_it",
            area="Sales",
            urgency=4,
            impact=5,
            data_objects=["products", "stock"],
            root_cause="No online catalogue",
            solution_outline="Online store",
            outcome="Sell online",
        ),
        Issue(
            title="Mobile ERP app",
            stage="need_answer",
            open_question="Kitne staff ERP app use karenge?",
            area="Operations",
            data_objects=["stock", "orders"],
        ),
        Issue(title="Features PDF", stage="noted", area="Operations"),
    ],
    links=[
        IssueLink(
            a=0,
            b=1,
            type="shared_data",
            confidence=0.9,
            reason="same stock",
            benefit="One stock list, no overselling",
        ),
        # Unsure: waits for the team, never shown to the customer.
        IssueLink(a=2, b=1, type="part_of", confidence=0.6, reason="part of ERP"),
        IssueLink(a=0, b=2, type="same_cause", confidence=0.2, reason="weak"),
    ],
)


def _mock(monkeypatch, report: IssueReport) -> None:
    async def complete(self, scope, output, **kwargs):
        return SimpleNamespace(value=report, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)


async def _linked_chat(app, provider, db, monkeypatch):
    business = await _business_with_chat(app, provider, db, monkeypatch)
    customer = await _sign_in(app, provider)
    conversation_id = (await customer.get(f"{PORTAL}/conversations")).json()[0]["id"]
    _mock(monkeypatch, LINKED)
    await customer.get(f"{PORTAL}/conversations/{conversation_id}/issues")
    return business, customer, conversation_id


async def test_links_group_solutions_and_only_sure_links_reach_the_customer(
    app, provider, business_db, monkeypatch
):
    business, customer, conversation_id = await _linked_chat(
        app, provider, business_db, monkeypatch
    )
    listed = (await customer.get(f"{PORTAL}/conversations")).json()[0]
    assert [(x["a_title"], x["b_title"]) for x in listed["links"]] == [
        ("Furniture website", "Mobile ERP app")
    ]
    site, erp, pdf = listed["issues"]
    assert site["solution_id"] == erp["solution_id"] != pdf["solution_id"]
    assert site["linked"] == 1 and pdf["linked"] == 0
    assert site["urgency"] == 4 and site["area"] == "Sales"
    # The team sees the unsure link in its review queue and confirms it.
    board = (await business.get("/api/v1/pi-app/problems")).json()
    [pending] = board["pending_links"]
    assert pending["a_title"] == "Features PDF" and pending["b_title"] == "Mobile ERP app"
    confirmed = await business.post(
        "/api/v1/pi-app/problems/links",
        json={
            "conversation_id": conversation_id,
            "a_title": "Mobile ERP app",
            "b_title": "Features PDF",
            "action": "confirm",
        },
    )
    assert confirmed.status_code == 200 and confirmed.json()["pending_links"] == []
    listed = (await customer.get(f"{PORTAL}/conversations")).json()[0]
    assert len(listed["links"]) == 2
    assert len({i["solution_id"] for i in listed["issues"]}) == 1  # one system fixes all
    await business.aclose()
    await customer.aclose()


async def test_not_related_removes_the_line_for_good(app, provider, business_db, monkeypatch):
    business, customer, conversation_id = await _linked_chat(
        app, provider, business_db, monkeypatch
    )
    headers = {"x-csrf-token": customer.cookies[CSRF_COOKIE]}
    gone = await customer.post(
        f"{PORTAL}/conversations/{conversation_id}/links/not-related",
        json={"a_title": "Mobile ERP app", "b_title": "Furniture website"},
        headers=headers,
    )
    assert gone.status_code == 200
    listed = (await customer.get(f"{PORTAL}/conversations")).json()[0]
    assert listed["links"] == []
    assert len({i["solution_id"] for i in listed["issues"]}) == 3
    # pi reads the chat again (a new message) and suggests the same link: it stays gone.
    conversation = await business_db.get(PiConversation, conversation_id)
    await business_db.refresh(conversation)
    conversation.last_message_at = datetime.now(UTC)
    await business_db.commit()
    await customer.get(f"{PORTAL}/conversations/{conversation_id}/issues")
    listed = (await customer.get(f"{PORTAL}/conversations")).json()[0]
    assert listed["links"] == []
    await business.aclose()
    await customer.aclose()


async def test_timeline_shows_what_pi_noticed_and_what_people_did(
    app, provider, business_db, monkeypatch
):
    business, customer, conversation_id = await _linked_chat(
        app, provider, business_db, monkeypatch
    )
    events = (await customer.get(f"{PORTAL}/conversations/{conversation_id}/timeline")).json()
    kinds = [e["kind"] for e in events]
    assert kinds.count("problem.noted") == 3 and "link.found" in kinds
    assert "client.wrote" in kinds and "pi.asked" in kinds
    assert all(e["actor"] in ("pi", "you", "team") for e in events)
    assert events == sorted(events, key=lambda e: e["at"], reverse=True)
    await business.aclose()
    await customer.aclose()


async def test_cards_are_signed_expire_and_show_no_chat(app, provider, business_db, monkeypatch):
    business, customer, conversation_id = await _linked_chat(
        app, provider, business_db, monkeypatch
    )
    settings = app.state.settings
    from uuid import UUID

    token = card_token(settings, UUID(conversation_id), "map")
    assert read_card(settings, token)["kind"] == "map"
    assert read_card(settings, token[:-2] + "xx") is None  # forged
    anonymous = pi_client(app)
    data = (await anonymous.get(f"{PORTAL}/card/{token}")).json()
    assert data["kind"] == "map" and len(data["issues"]) == 3 and len(data["links"]) == 1
    assert "Website chahiye" not in json.dumps(data)
    assert (await anonymous.get(f"{PORTAL}/card/not-a-token")).status_code == 404
    await anonymous.aclose()
    await business.aclose()
    await customer.aclose()


def test_the_most_useful_card_is_picked():
    report = {
        "language": "en",
        "issues": [
            {"title": "Website", "stage": "on_it", "ball_with": "team", "next_step": "Team: x"},
            {
                "title": "ERP",
                "stage": "need_answer",
                "ball_with": "client",
                "open_question": "How many staff?",
            },
        ],
        "links": [{"status": "auto", "a_title": "Website", "b_title": "ERP"}],
        "new_events": [
            {"kind": "stage.changed", "title": "ERP", "to": "need_answer"},
            {"kind": "link.found", "announce": True, "detail": "same stock"},
        ],
    }
    kind, _, caption = engine.pick_card(report)
    assert kind == "map" and "1 connection" in caption
    report["new_events"] = report["new_events"][:1]
    kind, index, caption = engine.pick_card(report)
    assert (kind, index) == ("journey", 1) and "How many staff?" in caption
    report["new_events"] = [{"kind": "problem.noted", "title": "ERP"}]
    assert engine.pick_card(report) is None  # "noted" alone never gets a card


async def _age(db, conversation_id, *, client_hours=None, team_hours=None, inbound_hours=None):
    conversation = await db.get(PiConversation, conversation_id)
    await db.refresh(conversation)
    now = datetime.now(UTC)
    brief = dict(conversation.service_brief)
    report = dict(brief["customer_issues"])
    report["waiting"] = {
        "client": (now - timedelta(hours=client_hours)).isoformat() if client_hours else None,
        "team": (now - timedelta(hours=team_hours)).isoformat() if team_hours else None,
    }
    brief["customer_issues"] = report
    conversation.service_brief = brief
    if inbound_hours is not None:
        conversation.last_inbound_at = now - timedelta(hours=inbound_hours)
    await db.commit()
    return conversation


async def test_the_customer_gets_one_nudge_quoting_the_question_at_20_hours(
    app, provider, business_db, monkeypatch
):
    business, customer, conversation_id = await _linked_chat(
        app, provider, business_db, monkeypatch
    )
    monkeypatch.setattr(engine, "prayer_or_quiet", lambda policy, now=None: False)
    ctx = worker_ctx(app, business_db)
    await _age(business_db, conversation_id, client_hours=5, inbound_hours=5)
    assert await engine.run_ladder(ctx) == []  # too early
    await _age(business_db, conversation_id, client_hours=20.5, inbound_hours=20.5)
    [queued] = await engine.run_ladder(ctx)
    message = await business_db.get(PiMessage, queued)
    assert "Kitne staff ERP app use karenge?" in message.body and "Mobile ERP app" in message.body
    assert await engine.run_ladder(ctx) == []  # once per question
    await business.aclose()
    await customer.aclose()


async def test_stop_and_waiting_on_someone_else_silence_the_ladder(
    app, provider, business_db, monkeypatch
):
    business, customer, conversation_id = await _linked_chat(
        app, provider, business_db, monkeypatch
    )
    monkeypatch.setattr(engine, "prayer_or_quiet", lambda policy, now=None: False)
    ctx = worker_ctx(app, business_db)
    headers = {"x-csrf-token": customer.cookies[CSRF_COOKIE]}
    await customer.post(
        f"{PORTAL}/conversations/{conversation_id}/waiting", json={"days": 5}, headers=headers
    )
    await _age(business_db, conversation_id, client_hours=21, inbound_hours=21)
    assert await engine.run_ladder(ctx) == []
    await customer.post(
        f"{PORTAL}/conversations/{conversation_id}/waiting", json={"days": 0}, headers=headers
    )
    inbound = await business_db.scalar(
        select(PiMessage).where(
            PiMessage.conversation_id == conversation_id, PiMessage.direction == "inbound"
        )
    )
    inbound.body = "band karo please"
    await business_db.commit()
    assert await engine.run_ladder(ctx) == []
    conversation = await business_db.get(PiConversation, conversation_id)
    await business_db.refresh(conversation)
    assert conversation.service_brief["reminder_consent"] == "declined"
    await business.aclose()
    await customer.aclose()


async def test_the_team_is_alerted_when_a_customer_waits_on_it(
    app, provider, business_db, monkeypatch
):
    business, customer, conversation_id = await _linked_chat(
        app, provider, business_db, monkeypatch
    )
    monkeypatch.setattr(engine, "prayer_or_quiet", lambda policy, now=None: False)
    ctx = worker_ctx(app, business_db)
    conversation = await _age(business_db, conversation_id, team_hours=25, inbound_hours=13)
    queued = await engine.run_ladder(ctx)
    kinds = [
        (n.title, n.severity)
        for n in await business_db.scalars(
            select(Notification).where(
                Notification.tenant_id == conversation.tenant_id,
                Notification.kind == "pi.team_sla",
            )
        )
    ]
    assert sorted(kinds) == [
        ("A customer has waited 12h for the team", "info"),
        ("A customer has waited 24h for the team", "warning"),
    ]
    statuses = [await business_db.get(PiMessage, q) for q in queued]
    assert any("Furniture website" in m.body and "update" in m.body for m in statuses)
    await business.aclose()
    await customer.aclose()
