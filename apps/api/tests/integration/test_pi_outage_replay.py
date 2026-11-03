"""Platform spec v1.4, 17.7 (HO1): the model is down, the owner gets one holding line, nothing is
lost, and the queued turn is answered first (and once) when the model is back."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select, update
from test_pi_brain_flow import brain_on
from test_pi_industry_context import contexts, scripted
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import turn

from app.ai.gateway import GatewayUnavailable
from app.ai.manager import LLMManager
from app.modules.pi import outage, runtime
from app.modules.pi.models import PiMessage

pytestmark = pytest.mark.integration


def model_down(monkeypatch) -> None:
    async def complete(self, scope, output, **kwargs):
        if kwargs.get("purpose") == "pi_problem_extract":
            return SimpleNamespace(value=output(), response=SimpleNamespace(attempts=[]))
        raise GatewayUnavailable()

    monkeypatch.setattr(LLMManager, "complete_structured", complete)


async def inbound_rows(db, conversation) -> list[PiMessage]:
    return list(
        await db.scalars(
            select(PiMessage)
            .where(PiMessage.conversation_id == conversation.id, PiMessage.direction == "inbound")
            .order_by(PiMessage.created_at)
            .execution_options(populate_existing=True)
        )
    )


async def make_due(db, conversation) -> None:
    """Move the backoff and the clock of every queued message into the past."""
    # (one outer transaction in tests stamps every row alike: spread them as real time would)
    rows = sorted(await inbound_rows(db, conversation), key=lambda r: r.provider_message_id)
    for i, row in enumerate(rows):
        await db.execute(
            update(PiMessage)
            .where(PiMessage.id == row.id)
            .values(created_at=datetime.now(UTC) - timedelta(minutes=10 - i))
        )
        if row.error_code == outage.CODE:
            state = outage.state_of(row)
            state["next_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
            row.media = {**row.media, "outage": state}
    await db.commit()


async def test_outage_holds_once_queues_and_answers_first_on_recovery(
    api, business_db, monkeypatch
):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await brain_on(api)
    model_down(monkeypatch)
    await pi.process("My shop stock keeps running out and I am very tired of it", "out-1")
    conversation = await pi.conversation()
    first = (await inbound_rows(business_db, conversation))[0]
    assert (first.status, first.error_code) == ("skipped", outage.CODE)
    held = await pi.outbound()
    assert len(held) == 1 and held[0].idempotency_key.startswith(outage.KEY_PREFIX)
    assert "saved" in held[0].body and "minutes" not in held[0].body  # no promised time
    assert " AI " in f" {held[0].body} "  # pi's first words in this chat say what pi is (R-DISC-01)
    # a second message in the same outage: kept, and no second holding line
    await pi.process("Also the staff keep making excuses", "out-2")
    assert len(await pi.outbound()) == 1
    rows = await inbound_rows(business_db, conversation)
    assert [r.error_code for r in rows] == [outage.CODE, outage.CODE]
    # still inside the backoff: the sweeper does nothing
    await runtime.sweep_pi(pi.ctx)
    assert len(await pi.outbound()) == 1
    # the model is back: the newest message is replayed and covers both, once
    prompts = scripted(monkeypatch, turn(reply="That sounds exhausting. Which items run out?"))
    await make_due(business_db, conversation)
    await runtime.sweep_pi(pi.ctx)
    await pi.deliver_all()
    real = [m for m in await pi.outbound() if not outage.is_outage_key(m.idempotency_key)]
    assert (
        len(real) == 1
        and "That sounds exhausting" in real[0].body
        and real[0].body.startswith("Hi, I'm pi, an AI")
    )
    context = contexts(prompts)[0]
    assert context["burst_texts"] == ["My shop stock keeps running out and I am very tired of it"]
    assert "while pi was down" in context["owner_turn_note"]
    # settled: nothing is replayed again, no second answer
    await runtime.sweep_pi(pi.ctx)
    await runtime.sweep_pi(pi.ctx)
    assert all(r.error_code != outage.CODE for r in await inbound_rows(business_db, conversation))
    assert len([m for m in await pi.outbound() if m.sender_type == "ai"]) == 1
    await pi.close()


async def test_a_half_hour_update_and_a_two_hour_alert(api, business_db, monkeypatch):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await brain_on(api)
    model_down(monkeypatch)
    await pi.process("My shop stock keeps running out", "late-1")
    conversation = await pi.conversation()
    row = (await inbound_rows(business_db, conversation))[0]
    state = outage.state_of(row)
    state["queued_at"] = (datetime.now(UTC) - timedelta(minutes=31)).isoformat()
    row.media = {**row.media, "outage": state}
    await business_db.commit()
    await runtime.sweep_pi(pi.ctx)
    await runtime.sweep_pi(pi.ctx)
    updates = [m for m in await pi.outbound() if ":update:" in (m.idempotency_key or "")]
    assert len(updates) == 1  # one update, never repeated
    await business_db.refresh(row)
    assert outage.state_of(row).get("alerted") is None
    state = outage.state_of(row)
    state["queued_at"] = (datetime.now(UTC) - timedelta(hours=2, minutes=1)).isoformat()
    row.media = {**row.media, "outage": state}
    await business_db.commit()
    await runtime.sweep_pi(pi.ctx)
    await business_db.refresh(row)
    assert outage.state_of(row).get("alerted")
    assert (await api.get("/api/v1/pi/requests")).json()["items"]  # a person is asked
    await pi.close()
