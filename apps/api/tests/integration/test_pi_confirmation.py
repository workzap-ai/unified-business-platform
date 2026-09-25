import pytest
from sqlalchemy import func, select
from test_pi_runtime import setup_pi, webhook
from test_service_lifecycle import create

from app.modules.orders.models import Order
from app.modules.pi.models import PiMessage, PiPendingAction
from app.modules.pi.runtime import process_pi_event, send_pi_message

pytestmark = pytest.mark.integration


async def test_customer_confirmation_requires_delivered_summary_and_exact_reference(
    api, business_db
):
    app, ctx = await setup_pi(api, business_db)
    assert (
        await api.patch("/api/v1/settings/business", json={"business_type": "product_business"})
    ).status_code == 200
    await create(
        api,
        "catalog/products",
        {
            "name": "Website",
            "offering_type": "product",
            "variants": [{"sku": "WEB", "name": "Standard", "price": "1250.00", "currency": "USD"}],
        },
    )
    await webhook(api, app, "order website")
    await process_pi_event(ctx, *app.state.queue.jobs[-1][1])
    conversation = (await api.get("/api/v1/pi/conversations")).json()["items"][0]
    order = await business_db.scalar(
        select(Order).where(Order.customer_id == conversation["customer_id"])
    )
    assert order.status == "draft"
    summary = await business_db.scalar(
        select(PiMessage).where(
            PiMessage.direction == "outbound",
            PiMessage.conversation_id == conversation["id"],
        )
    )
    assert f"CONFIRM {order.number}" in summary.body
    await webhook(api, app, f"CONFIRM {order.number}", mid="before-summary")
    await process_pi_event(ctx, *app.state.queue.jobs[-1][1])
    assert order.status == "draft"
    await send_pi_message(ctx, str(summary.id))
    await webhook(api, app, "yes", mid="ambiguous-yes")
    await process_pi_event(ctx, *app.state.queue.jobs[-1][1])
    assert order.status == "draft"
    await webhook(api, app, f"CONFIRM {order.number}", mid="explicit-confirmation")
    args = app.state.queue.jobs[-1][1]
    await process_pi_event(ctx, *args)
    await process_pi_event(ctx, *args)
    await business_db.refresh(order)
    from app.workflows.models import WorkflowRun

    results = list(await business_db.scalars(select(WorkflowRun)))
    assert order.status == "confirmed", [(x.tool_key, x.status, x.error_code) for x in results]
    pending = await business_db.scalar(
        select(PiPendingAction).where(PiPendingAction.conversation_id == conversation["id"])
    )
    assert pending.status == "confirmed"
    assert (
        await business_db.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.customer_id == conversation["customer_id"])
        )
        == 1
    )
    await ctx["http"].aclose()
