"""The team's view of one customer: who they are (what they told pi), their projects
with the journey, and their requests with the links between them (the Problem Map)."""

from uuid import UUID

import pytest
from test_pi_deals import _customer_in_chat, _lead
from test_pi_pipeline import pi_workspace

from app.modules.pi.models import PiConversation

pytestmark = pytest.mark.integration


async def test_overview_has_profile_projects_and_the_problem_map(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    customer_id, conversation = await _customer_in_chat(pi)
    lead_id = await _lead(pi, customer_id, conversation)
    row = await pi.db.get(PiConversation, conversation.id)
    row.language = "en"
    row.service_brief = {
        **(row.service_brief or {}),
        "customer_profile": {
            "business_name": "Crescent Bakers",
            "business_type": "Bakery chain in Lahore",
            "role": "Owner",
        },
        "customer_issues": {
            "headline": "Two requests, one shared stock system",
            "issues": [
                {"title": "Online shop", "stage": "on_it", "ball_with": "team", "impact": 5},
                {"title": "Stock app", "stage": "need_answer", "ball_with": "client"},
            ],
            "links": [
                {
                    "a": 0,
                    "b": 1,
                    "a_title": "Online shop",
                    "b_title": "Stock app",
                    "type": "shared_data",
                    "reason": "Both use the same stock",
                    "benefit": "One stock list",
                    "confidence": 0.9,
                    "status": "auto",
                },
                {
                    "a": 0,
                    "b": 1,
                    "a_title": "Online shop",
                    "b_title": "Stock app",
                    "type": "same_cause",
                    "reason": "Under review",
                    "confidence": 0.6,
                    "status": "pending_review",
                },
            ],
        },
    }
    await pi.db.commit()

    got = await api.get(f"/api/v1/customers/{customer_id}/pi-overview")
    assert got.status_code == 200, got.text
    body = got.json()
    profile = body["profile"]
    assert profile["business_name"] == "Crescent Bakers"
    assert profile["business_type"] == "Bakery chain in Lahore"
    assert profile["name"] == "Ayesha Khan" and profile["language"] == "en"
    assert profile["chats"] == 1 and profile["returning"] is False

    [project] = body["projects"]
    assert project["lead_id"] == lead_id and project["steps_total"] >= 9
    assert project["next"]["title"]

    titles = [i["title"] for i in body["issues"]]
    # pi's analysis, then the confirmed projects of the brief it didn't cover.
    assert titles == ["Online shop", "Stock app", "Logo", "Website"]
    assert [link["type"] for link in body["links"]] == ["shared_data"]  # review ones hidden
    assert body["counts"] == {"waiting_on_them": 1, "waiting_on_us": 3, "done": 0, "paused": 0}
    assert body["headline"].startswith("Two requests")
    assert UUID(body["issues"][0]["conversation_id"]) == conversation.id
    await pi.close()
