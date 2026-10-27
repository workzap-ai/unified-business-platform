"""The staff review view: map, dials, diagnosis, handover reason, box and alerts, for staff only,
read-only, and never across workspaces."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import func, select
from test_pi_management import member_client
from test_pi_pipeline import pi_workspace

from app.modules.pi.box_models import PiMapVersion, PiOfferLog, PiSolutionBox
from app.modules.pi.models import PiConversation, PiHandoff
from app.modules.pi.problem_models import PiProblem, PiProblemLink
from app.modules.pi.think_models import PiHypothesis, PiMoveLog
from app.modules.pi_saas.models import PiStaffRequest

pytestmark = pytest.mark.integration
R = "/api/v1/pi/review"


def scoped(conversation):
    return {"tenant_id": conversation.tenant_id, "environment_id": conversation.environment_id}


async def seed(pi, db):
    """A chat with a map of two linked problems, a diagnosis, a handoff and a request."""
    await pi.process("My shop stock keeps running out, call 0311 2546598", "rv-1")
    await pi.process("kahin aur jaun ga, bar bar same sawal", "rv-2")
    await pi.process("stop asking, jaldi batao", "rv-3")
    conversation = await pi.conversation()
    where = scoped(conversation)
    customer = conversation.customer_id
    a = PiProblem(
        **where,
        customer_id=customer,
        conversation_id=conversation.id,
        number=1,
        title="Best-sellers run out, card 4111 1111 1111 1111",
        category="stock_inventory",
        subtype="stockout",
        goal_verb="fix",
        status="confirmed",
        tags=["rank:1"],
        raised_voluntarily=True,
    )
    b = PiProblem(
        **where,
        customer_id=customer,
        conversation_id=conversation.id,
        number=2,
        title="Cash does not match",
        category="cash_collections",
        status="in_document",
    )
    c = PiProblem(
        **where,
        customer_id=customer,
        number=3,
        title="Late deliveries",
        category="orders_fulfilment",
        status="parked",
    )
    db.add_all([a, b, c])
    await db.flush()
    db.add_all(
        [
            PiProblemLink(
                **where,
                from_id=a.id,
                to_id=b.id,
                type="causes",
                evidence="pi_inferred",
                status="suggested",
            ),
            PiMapVersion(**where, customer_id=customer, version=1, map_json={}),
        ]
    )
    shared = PiMapVersion(**where, customer_id=customer, version=2, map_json={})
    db.add(shared)
    db.add_all(
        [
            PiMoveLog(
                **where,
                conversation_id=conversation.id,
                move="ask",
                reason="why",
                had_question=True,
                created_at=datetime(2026, 10, 27, 9, 0, tzinfo=UTC),
            ),
            PiMoveLog(
                **where,
                conversation_id=conversation.id,
                move="give_ideas",
                reason="asked",
                created_at=datetime(2026, 10, 27, 9, 5, tzinfo=UTC),
            ),
            PiHypothesis(
                **where,
                conversation_id=conversation.id,
                text="Reorders are late",
                status="open",
                confidence="low",
            ),
            PiHypothesis(
                **where,
                conversation_id=conversation.id,
                text="Ignored guess",
                status="open",
                ignored=True,
            ),
            PiOfferLog(**where, conversation_id=conversation.id, rule="R1", allowed=True),
            PiOfferLog(
                **where,
                conversation_id=conversation.id,
                rule="B",
                allowed=False,
                blocked_reason="B3: map not reviewed",
            ),
            PiSolutionBox(
                **where,
                customer_id=customer,
                state="collecting",
                reviewer="Sara",
                owner_ranking=["P1"],
            ),
        ]
    )
    handoff = PiHandoff(
        **where,
        conversation_id=conversation.id,
        customer_id=customer,
        reason="customer_request",
        summary="Owner wants a person, phone 0311 2546598",
        created_by_label="System",
    )
    db.add(handoff)
    request = PiStaffRequest(
        **where,
        conversation_id=conversation.id,
        customer_id=customer,
        question="What does the full set cost?",
        kind="price_request",
    )
    db.add(request)
    request.created_at = datetime(2020, 1, 1, tzinfo=UTC)  # long before the pi replies
    await db.flush()
    conversation.service_brief = {
        "expert_diag": {
            "problem": "Best-sellers run out",
            "causes": ["Reorders are late", "No stock count"],
            "question": "When did you last count the shelves?",
            "at": "2026-10-27T10:00:00+00:00",
        },
        "ideas_given": 3,
        "ideas_problems": [str(a.id), str(a.id), str(b.id)],
    }
    conversation.mode = "human"
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def test_staff_see_the_whole_briefing(api, business_db):
    pi = await pi_workspace(api, business_db)
    conversation = await seed(pi, business_db)
    response = await api.get(f"{R}/conversations/{conversation.id}")
    assert response.status_code == 200, response.text
    body = response.json()

    nodes = {n["id"]: n for n in body["map"]["nodes"]}
    assert set(nodes) == {"P1", "P2", "P3"}
    assert (nodes["P1"]["status"], nodes["P1"]["rank"], nodes["P1"]["goal_verb"]) == (
        "confirmed",
        1,
        "fix",
    )
    assert nodes["P1"]["raised_voluntarily"] is True and nodes["P1"]["subtype"] == "stockout"
    assert nodes["P2"]["status"] == "in_box" and nodes["P3"]["status"] == "parked"
    assert body["map"]["links"] == [
        {"from": "P1", "to": "P2", "type": "causes", "evidence": "pi_inferred"}
    ]
    assert body["map"]["version"] == 2 and body["map"]["shared_at"] is None
    assert body["map"]["up_to_date_with_owner"] is False

    assert set(body["thinking"]["dials"]) == {
        "openness",
        "pace",
        "mode",
        "trust_trend",
        "fatigue",
    }
    assert body["thinking"]["posture"] and body["thinking"]["messages_read"] == 3
    assert [m["move"] for m in body["thinking"]["moves"]] == ["give_ideas", "ask"]
    assert [h["text"] for h in body["thinking"]["hypotheses"]] == ["Reorders are late"]
    assert body["thinking"]["hypotheses"][0]["confirmed_by_owner"] is False

    assert body["diagnosis"]["main_problem"] == "Best-sellers run out"
    assert body["diagnosis"]["suggested_next_question"].startswith("When did you last count")
    ideas = body["ideas"]
    assert (ideas["given_in_chat"], ideas["per_problem_cap"], ideas["per_business_cap"]) == (
        3,
        2,
        8,
    )
    assert ideas["business_remaining"] == 5
    assert sorted(ideas["rounds_by_problem"].values()) == [1, 2]

    handoff = body["handover"]["handoff"]
    assert handoff["reason"] == "customer_request" and handoff["origin"] == "owner_asked"
    assert "price_request" in {r["kind"] for r in body["handover"]["requests"]}

    assert body["box"]["box"]["reviewer"] == "Sara" and body["box"]["box"]["owner_ranking"] == [
        "P1"
    ]
    assert {(o["rule"], o["allowed"]) for o in body["box"]["offers"]} == {
        ("R1", True),
        ("B", False),
    }
    assert any(o["blocked_reason"] == "B3: map not reviewed" for o in body["box"]["offers"])

    keys = {a["key"] for a in body["labels"]["alerts"]}
    assert {"churn_risk", "frustration", "handoff_open"} <= keys
    assert body["labels"]["alerts"][0]["level"] == "red"
    assert {label["label"] for label in body["labels"]["message_labels"]} == {"Listening", "Ideas"}
    await pi.close()


async def test_the_view_never_shows_names_full_numbers_or_cards(api, business_db):
    pi = await pi_workspace(api, business_db)
    conversation = await seed(pi, business_db)
    text = (await api.get(f"{R}/conversations/{conversation.id}")).text
    for secret in ("2546598", "4111 1111", "4111111111111111", "+15551234567"):
        assert secret not in text
    assert "customer_name" not in text
    attention = (await api.get(f"{R}/attention")).text
    assert "2546598" not in attention
    await pi.close()


async def test_the_attention_list_is_sorted_by_alert_and_skips_quiet_chats(api, business_db):
    pi = await pi_workspace(api, business_db)
    conversation = await seed(pi, business_db)
    listed = (await api.get(f"{R}/attention")).json()
    assert listed["total"] == 1
    item = listed["items"][0]
    assert item["conversation_id"] == str(conversation.id)
    assert [a["level"] for a in item["alerts"]][0] == "red"
    assert item["phone"].startswith("••••")
    await pi.close()


async def test_a_quiet_chat_is_not_listed(api, business_db):
    pi = await pi_workspace(api, business_db)
    await pi.process("hello", "rv-quiet")
    assert (await api.get(f"{R}/attention")).json() == {"items": [], "total": 0}
    conversation = await pi.conversation()
    body = (await api.get(f"{R}/conversations/{conversation.id}")).json()
    assert body["map"]["nodes"] == [] and body["map"]["version"] is None
    assert body["diagnosis"] is None and body["handover"]["handoff"] is None
    assert body["box"] == {"box": None, "offers": []}
    await pi.close()


async def test_a_handoff_word_is_told_apart_from_the_owner_asking(api, business_db):
    from app.modules.pi.models import PiAgentRun

    pi = await pi_workspace(api, business_db)
    conversation = await seed(pi, business_db)
    handoff = await business_db.scalar(select(PiHandoff))
    run = await business_db.scalar(select(PiAgentRun).limit(1))
    run.intent = "human_request"
    handoff.run_id = run.id
    await business_db.commit()
    body = (await api.get(f"{R}/conversations/{conversation.id}")).json()
    assert body["handover"]["handoff"]["origin"] == "keyword"
    await pi.close()


async def test_the_view_is_read_only(api, business_db):
    pi = await pi_workspace(api, business_db)
    conversation = await seed(pi, business_db)
    path = f"{R}/conversations/{conversation.id}"
    before = await business_db.scalar(select(func.count()).select_from(PiMapVersion))
    for _ in range(2):
        assert (await api.get(path)).status_code == 200
    business_db.expire_all()
    assert await business_db.scalar(select(func.count()).select_from(PiMapVersion)) == before
    for method in ("post", "put", "patch", "delete"):
        response = await getattr(api, method)(path)
        assert response.status_code in (404, 405)
    await pi.close()


async def test_non_staff_are_refused_and_staff_with_the_capability_are_not(api, business_db):
    pi = await pi_workspace(api, business_db)
    conversation = await seed(pi, business_db)
    viewer = await member_client(api, "viewer")
    sales = await member_client(api, "sales")
    support = await member_client(api, "support")
    try:
        for client in (viewer, sales):
            for path in (f"{R}/attention", f"{R}/conversations/{conversation.id}"):
                refused = await client.get(path)
                assert refused.status_code == 403, (path, refused.text)
                assert refused.json()["error"]["code"] == "FORBIDDEN"
        allowed = await support.get(f"{R}/conversations/{conversation.id}")
        assert allowed.status_code == 200, allowed.text
    finally:
        for client in (viewer, sales, support):
            await client.aclose()
        await pi.close()


async def test_another_workspace_cannot_read_it(api, business_db):
    pi = await pi_workspace(api, business_db)
    conversation = await seed(pi, business_db)
    api.cookies.clear()
    other = await pi_workspace(api, business_db, number="987654321")
    refused = await api.get(f"{R}/conversations/{conversation.id}")
    assert refused.status_code == 404
    assert (await api.get(f"{R}/attention")).json() == {"items": [], "total": 0}
    unknown = await api.get(f"{R}/conversations/{UUID(int=1)}")
    assert unknown.status_code == 404
    await other.close()
    assert await business_db.scalar(select(func.count()).select_from(PiConversation)) >= 1
