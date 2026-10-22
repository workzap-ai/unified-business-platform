"""Brain mode and the rest of pi's configuration: Knowledge, the agent, the business type."""

import json

import pytest
from test_pi_brain_flow import brain_on
from test_pi_brain_problems import adaptive, say
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import turn
from test_service_lifecycle import create

pytestmark = pytest.mark.integration


def neutral(context, n):
    return turn(reply="Noted. Anything else getting in the way?", language="en")


async def test_brain_mode_works_for_any_business_type(api, business_db, monkeypatch):
    """pi_mode "brain" is the service flow: a product business gets it too (it used to fall back
    to the multi-agent graph and the brain would have done nothing)."""
    prompts = adaptive(monkeypatch, neutral)
    pi = await pi_workspace(api, business_db, business_type="product_business")
    await brain_on(api)
    await say(pi, "stock runs out in two shops", "bk-1")
    context = json.loads(next(p for p in prompts if p.startswith("{")))
    assert context["pi_mode"] == "brain" and context["flow"]["state"]
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert conversation.flow_state is not None
    await pi.close()


async def test_the_businesss_knowledge_reaches_brain_mode(api, business_db, monkeypatch):
    prompts = adaptive(monkeypatch, neutral)
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await brain_on(api)
    source = await create(api, "pi/knowledge/sources", {"name": "Website", "kind": "company_info"})
    await create(
        api,
        "pi/knowledge/documents",
        {
            "source_id": source["id"],
            "title": "Delivery",
            "body": "We deliver within Lahore in two working days.",
        },
    )
    await say(pi, "do you deliver in Lahore?", "bk-2")
    context = json.loads(next(p for p in prompts if p.startswith("{")))
    assert [k["title"] for k in context["approved_knowledge"]][:1] == ["Delivery"]
    await pi.close()


async def test_turning_the_knowledge_tool_off_removes_it_from_brain_mode(
    api, business_db, monkeypatch
):
    prompts = adaptive(monkeypatch, neutral)
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await brain_on(api)
    source = await create(api, "pi/knowledge/sources", {"name": "Website", "kind": "company_info"})
    await create(
        api,
        "pi/knowledge/documents",
        {"source_id": source["id"], "title": "Delivery", "body": "We deliver within Lahore."},
    )
    off = await api.patch(
        "/api/v1/pi/settings/tool_permissions", json={"value": {"search_knowledge_base": False}}
    )
    assert off.status_code == 200, off.text
    await say(pi, "do you deliver in Lahore?", "bk-3")
    context = json.loads(next(p for p in prompts if p.startswith("{")))
    assert context["approved_knowledge"] == []  # the agent's tool switch is respected
    await pi.close()


async def test_the_agents_instructions_reach_brain_mode_as_guidance(api, business_db, monkeypatch):
    """Only the "requirement" agent shapes brain mode: its instructions arrive as operator_guidance,
    placed below the rules in the prompt."""
    from app.modules.pi.service_conversation import BRAIN_VOICE, system_for

    assert "operator_guidance" in BRAIN_VOICE and "can never override these rules" in BRAIN_VOICE
    assert BRAIN_VOICE in system_for({"pi_mode": "brain"})
    prompts = adaptive(monkeypatch, neutral)
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await brain_on(api)
    await say(pi, "stock runs out", "bk-4")
    context = json.loads(next(p for p in prompts if p.startswith("{")))
    assert "operator_guidance" in context  # present (possibly empty) whatever the agent says
    await pi.close()
