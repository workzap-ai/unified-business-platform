import pytest
from sqlalchemy import select
from test_pi_runtime import setup_pi, webhook
from test_service_lifecycle import create

from app.modules.pi.models import PiMessage, PiToolCall
from app.modules.pi.runtime import process_pi_event

pytestmark = pytest.mark.integration


async def test_configuration_knowledge_analytics_and_policy(api, business_db, monkeypatch):
    import sys

    def expose_error(*args, **kwargs):
        error = sys.exc_info()[1]
        if error:
            raise error

    monkeypatch.setattr("app.core.middleware.logger.error", expose_error)
    app, ctx = await setup_pi(api, business_db)
    for path in (
        "settings",
        "agents",
        "tools",
        "overview",
        "analytics?range=30",
        "whatsapp/events",
    ):
        response = await api.get(f"/api/v1/pi/{path}")
        assert response.status_code == 200, (path, response.text)
    agents = (await api.get("/api/v1/pi/agents")).json()
    agent = next(x for x in agents if x["key"] == "sales_order")
    version = await create(
        api,
        f"pi/agents/{agent['id']}/versions",
        {
            "instructions": "Route requests for proposals to quote.",
            "model_alias": "fast",
            "temperature": "0.10",
            "note": "Test publication",
        },
    )
    assert version["version"] == 2
    rolled = await create(api, f"pi/agents/{agent['id']}/versions/{version['id']}/rollback", {})
    assert rolled["version"] == 3
    preview = await create(api, "pi/agent-test", {"body": "website quote"})
    assert preview["simulated"] and preview["intent"] == "quote"
    source = await create(api, "pi/knowledge/sources", {"name": "Service terms", "kind": "policy"})
    document = await create(
        api,
        "pi/knowledge/documents",
        {
            "source_id": source["id"],
            "title": "Revisions",
            "body": "Website engagements include two rounds of revisions.",
        },
    )
    assert document["status"] == "ready" and document["chunk_count"] == 1
    assert (await create(api, f"pi/knowledge/documents/{document['id']}/retry", {}))[
        "id"
    ] == document["id"]
    duplicate = await create(
        api,
        "pi/knowledge/documents",
        {
            "source_id": source["id"],
            "title": "Duplicate",
            "body": "Website engagements include two rounds of revisions.",
        },
    )
    assert duplicate["id"] == document["id"]
    response = await api.put(
        f"/api/v1/pi/agents/{agent['id']}/tools/search_products", json={"enabled": False}
    )
    assert response.status_code == 200 and "search_products" not in response.json()["tools"]
    await webhook(api, app, "website pricing")
    await process_pi_event(ctx, *app.state.queue.jobs[-1][1])
    assert (await api.get("/api/v1/pi/handoffs")).json()[0]["reason"] == "tool_failure"
    conversations = (await api.get("/api/v1/pi/conversations")).json()["items"]
    cid = conversations[0]["id"]
    context = await api.get(f"/api/v1/pi/conversations/{cid}/context")
    assert context.status_code == 200, context.text
    assert len(context.json()["runs"]) == 1
    messages = (await api.get(f"/api/v1/pi/conversations/{cid}/messages")).json()
    assert messages[0]["media"] is None
    analytics = (await api.get("/api/v1/pi/analytics?range=7")).json()
    assert analytics["totals"]["conversations"] == 1
    assert analytics["totals"]["handoffs"] == 1
    assert analytics["cost_estimate"] is None
    event = (await api.get("/api/v1/pi/whatsapp/events")).json()["items"][0]
    assert (await api.post(f"/api/v1/pi/whatsapp/events/{event['id']}/replay")).status_code == 422
    await ctx["http"].aclose()


async def test_quote_draft_uses_catalog_and_records_tool_audit(api, business_db):
    app, ctx = await setup_pi(api, business_db)
    await create(
        api,
        "catalog/products",
        {
            "name": "Website",
            "offering_type": "service",
            "variants": [{"sku": "WEB", "name": "Standard", "price": "1250.00", "currency": "USD"}],
        },
    )
    await webhook(api, app, "website quote")
    await process_pi_event(ctx, *app.state.queue.jobs[-1][1])
    outbound = await business_db.scalar(select(PiMessage).where(PiMessage.direction == "outbound"))
    assert "1250.00 USD" in outbound.body and "Draft" in outbound.body
    tools = list(await business_db.scalars(select(PiToolCall)))
    assert {t.tool_key for t in tools} == {
        "search_products",
        "create_quote_draft",
        "send_whatsapp_message",
    }
    assert all(t.status == "success" for t in tools)
    await ctx["http"].aclose()
