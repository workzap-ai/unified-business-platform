"""Erasing what pi keeps about a customer (spec R-PRIV-06, learning eval L11)."""

import pytest
from sqlalchemy import func, select
from test_pi_brain_problems import adaptive, create, problems_of, say, workspace
from test_pi_service_conversations import turn

from app.modules.pi.brain_erase import ERASED
from app.modules.pi.experience_models import PiExperience
from app.modules.pi.models import PiMessage
from app.modules.pi.problem_models import PiProblem
from app.modules.pi.quarantine_models import PiQuarantine

pytestmark = pytest.mark.integration


def noting(context, n):
    if "Best-sellers" in context["latest_customer_message"]:
        return turn(
            reply="Hi, I'm pi, an AI from Workzap. Noted. Anything else getting in the way?",
            language="en",
            problem_ops=[create("Best-sellers run out", "Best-sellers run out.")],
        )
    return turn(reply="Noted. Anything else getting in the way?", language="en")


async def count(db, model):
    return await db.scalar(select(func.count()).select_from(model))


async def test_erasing_a_customer_removes_their_notes_and_words_but_keeps_records(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, noting)
    pi = await workspace(api, business_db)
    await say(pi, "Best-sellers run out. My card is 4111 1111 1111 1111", "er-1")
    await say(pi, "also cashiers are late", "er-2")
    conversation, rows = await problems_of(business_db, pi)
    assert len(rows) == 1 and await count(business_db, PiQuarantine) == 1
    customer_id = conversation.customer_id

    # Nothing happens without an explicit confirmation.
    refused = await api.post(f"/api/v1/pi/brain-erasure/{customer_id}", json={})
    assert refused.status_code == 422, refused.text
    assert await count(business_db, PiProblem) == 1

    done = await api.post(f"/api/v1/pi/brain-erasure/{customer_id}", json={"confirm": True})
    assert done.status_code == 200, done.text
    result = done.json()
    assert result["removed"]["problems"] == 1 and result["removed"]["quarantine"] == 1
    assert result["removed"]["messages_cleared"] >= 4 and result["conversations"] == 1
    assert result["kept"] == {"documents": 0, "payments": 0}

    business_db.expire_all()
    assert await count(business_db, PiProblem) == 0
    assert await count(business_db, PiQuarantine) == 0
    assert await count(business_db, PiExperience) == 0
    bodies = (await business_db.scalars(select(PiMessage.body))).all()
    assert bodies and all(body == ERASED for body in bodies)
    await business_db.refresh(conversation)
    assert conversation.service_brief == {"erased": True}
    await pi.close()


async def test_only_that_customers_data_is_erased(api, business_db, monkeypatch):
    adaptive(monkeypatch, noting)
    pi = await workspace(api, business_db)
    await say(pi, "Best-sellers run out", "ot-1")
    other = await pi.inbound("Best-sellers run out here too", "ot-2", sender="15550000002")
    assert other.status_code == 200
    from app.modules.pi.runtime import process_pi_event

    name, args = pi.app.state.queue.jobs[-1]
    await process_pi_event(pi.ctx, *args)
    assert await count(business_db, PiProblem) == 2
    conversation = await pi.conversation()
    erased = await api.post(
        f"/api/v1/pi/brain-erasure/{conversation.customer_id}", json={"confirm": True}
    )
    assert erased.status_code == 200
    business_db.expire_all()
    assert await count(business_db, PiProblem) == 1  # the other customer's note is untouched
    await pi.close()
