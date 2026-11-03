"""G55 (platform spec v1.6, Live Audit 5 Part 7): the owner writes three messages in a row; one
reply covers all. The 28 October chat sent the four problem lines one by one and pi answered one
of them. Real database/webhook/worker; the model and WhatsApp are mocked."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from test_pi_brain_problems import say
from test_pi_pipeline_gap_flows import (
    chat,
    roomy_limits,  # noqa: F401  (autouse fixture)
)

from app.modules.pi.models import PiMessage
from app.modules.pi.runtime import process_pi_event

pytestmark = pytest.mark.integration


async def test_g55(api, business_db, monkeypatch):
    pi, prompts = await chat(api, business_db, monkeypatch)
    answered_before = len(await pi.outbound())
    conversation = await pi.conversation()
    lines = {"g55-1": "Sales: we use QB.", "g55-2": "Stock: about 10 crore, written on paper."}
    jobs = []
    for mid, text in lines.items():
        assert (await pi.inbound(text, mid)).status_code == 200
        jobs.append(pi.app.state.queue.jobs[-1][1])
    newer = PiMessage(  # the third message is already waiting when the first two are looked at
        tenant_id=conversation.tenant_id,
        environment_id=conversation.environment_id,
        conversation_id=conversation.id,
        direction="inbound",
        sender_type="customer",
        message_type="text",
        body="placeholder for the newer message",
        provider_message_id="newer-g55",
        status="received",
        created_at=datetime.now(UTC) + timedelta(seconds=30),
    )
    business_db.add(newer)
    await business_db.commit()
    for job in jobs:
        await process_pi_event(pi.ctx, *job)
    newer.status = "processed"
    rows = (
        await business_db.scalars(
            select(PiMessage).where(PiMessage.provider_message_id.in_(list(lines)))
        )
    ).all()
    assert {r.status for r in rows} == {"skipped"}
    now = datetime.now(UTC)
    for outbound in await pi.outbound():
        outbound.created_at = now - timedelta(hours=1)
    for offset, mid in ((10, "g55-1"), (5, "g55-2")):
        next(r for r in rows if r.provider_message_id == mid).created_at = now - timedelta(
            minutes=offset
        )
    await business_db.commit()

    await say(pi, "Cash: in and out do not match.", "g55-3")  # answers the whole burst
    assert (await pi.reply_to("g55-3")).body
    # one reply for the three messages: nothing was sent for the two that were waited out
    assert len(await pi.outbound()) == answered_before + 1
    model_input = json.loads([p for p in prompts if p.startswith("{")][-1])
    assert model_input["burst_texts"] == list(lines.values())  # both earlier lines are read
    assert model_input["latest_customer_message"] == "Cash: in and out do not match."
    await pi.close()
