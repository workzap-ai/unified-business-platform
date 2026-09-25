"""ToolRegistry: validation, permissions, toggles, takeover refusal and confirmation tokens."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select, update
from test_pi_pipeline import Pi, pi_workspace, stocked_router
from test_service_lifecycle import create

from app.modules.audit.models import AuditEvent
from app.modules.inventory.service import InventoryService
from app.modules.orders.models import Order
from app.modules.orders.schemas import OrderLineInput
from app.modules.orders.service import OrderService
from app.modules.pi.models import PiAgentRun, PiConversation, PiMessage, PiToolCall
from app.modules.pi.tools.catalog import TOOL_CATALOG
from app.modules.pi.tools.confirmation import issue
from app.modules.pi.tools.registry import ToolRegistry
from app.modules.products.models import EnvironmentProductInstallation

pytestmark = pytest.mark.integration


async def conversation_with_run(pi: Pi, mid: str = "wamid.tools-0") -> tuple[PiConversation, Any]:
    await pi.process("hello", mid)
    conversation = await pi.conversation()
    run = await pi.db.scalar(
        select(PiAgentRun).where(PiAgentRun.conversation_id == conversation.id)
    )
    return conversation, run


def test_catalog_is_complete_and_typed() -> None:
    assert set(TOOL_CATALOG) == {
        "search_customer",
        "get_customer",
        "get_customer_orders",
        "get_customer_balance",
        "search_products",
        "get_product",
        "check_inventory",
        "create_order_draft",
        "calculate_order_total",
        "create_order",
        "get_order",
        "get_invoice",
        "get_company_information",
        "create_quote_draft",
        "search_knowledge_base",
        "search_customer_memory",
        "create_handoff",
        "send_whatsapp_message",
    }
    assert [k for k, s in TOOL_CATALOG.items() if s.requires_confirmation] == ["create_order"]
    for spec in TOOL_CATALOG.values():
        described = spec.describe()
        assert described["input_schema"]["type"] == "object"
        assert described["permission"]


async def test_validation_permissions_toggles_and_features(
    api: httpx.AsyncClient, business_db: Any
) -> None:
    pi = await pi_workspace(api, business_db)
    product = await stocked_router(api)
    variant = product["variants"][0]["id"]
    service = await create(
        api,
        "catalog/products",
        {
            "name": "Router setup visit",
            "offering_type": "service",
            "variants": [{"sku": "SETUP", "name": "Visit", "price": "20.00", "currency": "USD"}],
        },
    )
    conversation, run = await conversation_with_run(pi)
    registry, scope = ToolRegistry(business_db), pi.scope()

    async def call(name: str, args: Any, **kwargs: Any) -> Any:
        return await registry.execute(scope, conversation, name, args, run=run, **kwargs)

    assert (await call("delete_everything", {})).error_code == "UNKNOWN_TOOL"
    for bad in (
        {"lines": [{"variant_id": variant, "quantity": 0}]},
        {"lines": [{"variant_id": variant, "quantity": 1, "unit_price": "0.01"}]},
        {"lines": []},
        {"lines": [{"variant_id": "not-a-uuid", "quantity": 1}]},
        "raw text from a model",
    ):
        result = await call("create_order_draft", bad)
        assert (result.ok, result.status, result.error_code) == (
            False,
            "invalid",
            "INVALID_ARGUMENTS",
        )
    mismatch = await call("get_customer", {"customer_id": str(uuid4())})
    assert mismatch.error_code == "CUSTOMER_MISMATCH"
    # Values are read from services: untracked offerings report no stock figure.
    stock = await call("check_inventory", {"variant_ids": [variant, service["variants"][0]["id"]]})
    assert stock.ok
    assert [(i["tracked"], i["available"]) for i in stock.data["items"]] == [
        (True, 5),
        (False, None),
    ]
    total = await call("calculate_order_total", {"lines": [{"variant_id": variant, "quantity": 3}]})
    assert total.data["total"] == "150.00" and total.data["lines"][0]["unit_price"] == "50.00"
    # Permission: the caller's scope must hold the tool permission.
    narrow = pi.scope("catalog.read", "pi.read")
    denied = await registry.execute(
        narrow, conversation, "check_inventory", {"variant_ids": [variant]}
    )
    assert (denied.status, denied.error_code) == ("denied", "PERMISSION_DENIED")
    # Workspace toggle, then agent-level toggle.
    assert (
        await api.put("/api/v1/pi/tools/check_inventory/enabled", json={"enabled": False})
    ).status_code == 200
    assert (await call("check_inventory", {"variant_ids": [variant]})).error_code == "TOOL_DISABLED"
    await api.put("/api/v1/pi/tools/check_inventory/enabled", json={"enabled": True})
    agents = {a["key"]: a for a in (await api.get("/api/v1/pi/agents")).json()}
    response = await api.put(
        f"/api/v1/pi/agents/{agents['sales_order']['id']}/tools/search_products",
        json={"enabled": False},
    )
    assert response.status_code == 200 and "search_products" not in response.json()["tools"]
    blocked = await call("search_products", {"query": "router"}, agent_key="sales_order")
    allowed = await call("search_products", {"query": "router"}, agent_key="support")
    assert blocked.error_code == "TOOL_DISABLED" and allowed.ok
    # Product feature gate.
    await business_db.execute(
        update(EnvironmentProductInstallation)
        .where(
            EnvironmentProductInstallation.tenant_id == UUID(pi.tenant_id),
            EnvironmentProductInstallation.environment_id == UUID(pi.environment_id),
        )
        .values(disabled_features=["orders"])
    )
    gated = await call("create_order_draft", {"lines": [{"variant_id": variant, "quantity": 1}]})
    assert gated.error_code == "PI_FEATURE_DISABLED"
    statuses = [
        c.status
        for c in await business_db.scalars(select(PiToolCall).where(PiToolCall.run_id == run.id))
    ]
    assert statuses.count("invalid") == 6 and "denied" in statuses
    audited = await business_db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.tenant_id == UUID(pi.tenant_id),
            AuditEvent.action == "pi.tool.create_order_draft",
        )
    )
    assert audited >= 1
    assert (
        await business_db.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.customer_id == conversation.customer_id)
        )
        == 0
    )
    await pi.close()


async def test_takeover_refuses_every_tool(api: httpx.AsyncClient, business_db: Any) -> None:
    pi = await pi_workspace(api, business_db)
    await stocked_router(api)
    conversation, run = await conversation_with_run(pi)
    assert (
        await api.post(f"/api/v1/pi/conversations/{conversation.id}/actions/takeover")
    ).status_code == 200
    registry = ToolRegistry(business_db)
    for name, args in (
        ("search_products", {"query": "router"}),
        ("send_whatsapp_message", {"body": "Hi"}),
        ("create_handoff", {"reason": "policy", "summary": "x"}),
    ):
        result = await registry.execute(pi.scope(), conversation, name, args, run=run)
        assert (result.ok, result.error_code) == (False, "HUMAN_TAKEOVER"), name
    await pi.close()


async def test_confirmation_token_happy_path_reuse_tamper_expiry_and_change(
    api: httpx.AsyncClient, business_db: Any
) -> None:
    pi = await pi_workspace(api, business_db)
    product = await stocked_router(api, stock=5)
    variant = product["variants"][0]["id"]
    conversation, run = await conversation_with_run(pi)
    registry, scope = ToolRegistry(business_db), pi.scope()

    async def call(name: str, args: Any, confirmation: str | None = None) -> Any:
        return await registry.execute(scope, conversation, name, args, confirmation, run=run)

    async def draft(quantity: int) -> tuple[dict[str, Any], Any, str]:
        result = await call(
            "create_order_draft", {"lines": [{"variant_id": variant, "quantity": quantity}]}
        )
        assert result.ok, result
        pending, token = await issue(business_db, scope, conversation, result.data)
        return result.data, pending, token

    def deliver(summary: str) -> None:
        business_db.add(
            PiMessage(
                tenant_id=conversation.tenant_id,
                environment_id=conversation.environment_id,
                conversation_id=conversation.id,
                direction="outbound",
                sender_type="ai",
                body=summary + "\nReply CONFIRM",
                status="delivered",
                provider_message_id=f"wamid.{uuid4().hex}",
            )
        )

    order, pending, token = await draft(2)
    assert order["status"] == "draft" and order["total"] == "100.00"
    args = {"order_id": order["id"]}
    assert (await call("create_order", args)).error_code == "CONFIRMATION_REQUIRED"
    assert (await call("create_order", args, token[:-1] + "0")).error_code in {
        "CONFIRMATION_INVALID",
        "SUMMARY_NOT_DELIVERED",
    }
    assert (await call("create_order", args, token)).error_code == "SUMMARY_NOT_DELIVERED"
    deliver(pending.summary)
    tampered = "f" * 64 if token != "f" * 64 else "e" * 64
    assert (await call("create_order", args, tampered)).error_code == "CONFIRMATION_INVALID"
    confirmed = await call("create_order", args, token)
    assert confirmed.ok and confirmed.data["status"] == "confirmed"
    await business_db.refresh(pending)
    assert pending.status == "confirmed"
    levels = await InventoryService(business_db, scope).availability([UUID(variant)])
    assert levels[UUID(variant)].available == 3
    reused = await call("create_order", args, token)
    assert reused.error_code == "CONFIRMATION_USED"
    # Expired.
    order2, pending2, token2 = await draft(1)
    deliver(pending2.summary)
    pending2.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await business_db.flush()
    expired = await call("create_order", {"order_id": order2["id"]}, token2)
    assert expired.error_code == "CONFIRMATION_EXPIRED"
    # Draft edited after the summary: the token no longer matches.
    order3, pending3, token3 = await draft(3)
    deliver(pending3.summary)
    await OrderService(business_db, scope).update_lines(
        UUID(order3["id"]), [OrderLineInput(variant_id=UUID(variant), quantity=4)]
    )
    changed = await call("create_order", {"order_id": order3["id"]}, token3)
    assert changed.error_code == "DRAFT_CHANGED"
    # A token for one conversation is useless in another.
    await pi.process("hello", "wamid.tools-other", sender="15550000002")
    other = await business_db.scalar(
        select(PiConversation).where(
            PiConversation.tenant_id == conversation.tenant_id,
            PiConversation.id != conversation.id,
        )
    )
    order4, pending4, token4 = await draft(4)
    deliver(pending4.summary)
    foreign = await registry.execute(
        scope, other, "create_order", {"order_id": order4["id"]}, token4, run=run
    )
    assert foreign.error_code in {"CONFIRMATION_INVALID", "CUSTOMER_MISMATCH"}
    for number in (order2["id"], order3["id"], order4["id"]):
        row = await business_db.get(Order, UUID(number))
        assert row is not None and row.status == "draft"
    await pi.close()


async def test_cross_tenant_records_are_unreachable(
    api: httpx.AsyncClient, business_db: Any
) -> None:
    alpha = await pi_workspace(api, business_db)
    alpha_product = await stocked_router(api)
    alpha_conversation, _ = await conversation_with_run(alpha, "wamid.alpha-0")
    api.cookies.clear()
    beta = await pi_workspace(api, business_db, number="987654321")
    await stocked_router(api)
    beta_conversation, beta_run = await conversation_with_run(beta, "wamid.beta-0")
    registry = ToolRegistry(business_db)
    draft = await registry.execute(
        beta.scope(),
        beta_conversation,
        "create_order_draft",
        {"lines": [{"variant_id": alpha_product["variants"][0]["id"], "quantity": 1}]},
        run=beta_run,
    )
    assert (draft.ok, draft.error_code) == (False, "RESOURCE_NOT_FOUND")
    product = await registry.execute(
        beta.scope(), beta_conversation, "get_product", {"product_id": alpha_product["id"]}
    )
    assert product.error_code == "RESOURCE_NOT_FOUND"
    foreign = await registry.execute(
        beta.scope(), alpha_conversation, "search_products", {"query": "router"}
    )
    assert foreign.error_code == "CONVERSATION_NOT_FOUND"
    assert (
        await business_db.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.customer_id == beta_conversation.customer_id)
        )
        == 0
    )
    await alpha.close()
    await beta.close()
