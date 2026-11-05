"""The shared memory block on a real database: it holds what the ledger recorded for ONE customer
of ONE workspace, another workspace never sees it, and an erased customer gives an empty block."""

import pytest
from test_pi_meeting_data import workspace

from app.modules.pi import brain_erase, memory_ledger, shared_memory

pytestmark = pytest.mark.integration


async def test_the_block_holds_the_customers_records_and_only_theirs(api, business_db):
    pi_a, conv_a, scope_a = await workspace(api, business_db, "399000001")
    pi_b, conv_b, scope_b = await workspace(api, business_db, "399000002")
    await memory_ledger.record_decision(
        business_db,
        scope_a,
        customer_id=conv_a.customer_id,
        kind="other",
        subject_ref="meeting:abc:def",
        actor="staff",
        owner_words="weekly stock count agreed",
    )
    mine = await shared_memory.brief(business_db, scope_a, conv_a.customer_id)
    assert mine and any("weekly stock count" in r["text"] for r in mine["records"])
    # the same customer id asked for from another workspace: nothing
    assert not (await shared_memory.brief(business_db, scope_b, conv_a.customer_id)).get("records")
    # the other workspace's own customer does not see it either
    other = await shared_memory.brief(business_db, scope_b, conv_b.customer_id)
    assert "weekly stock count" not in str(other)
    assert await shared_memory.brief(business_db, scope_a, None) == {}
    await pi_a.close()
    await pi_b.close()


async def test_an_erased_customer_gives_an_empty_block(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "399000003")
    await memory_ledger.record_decision(
        business_db,
        scope,
        customer_id=conv.customer_id,
        kind="other",
        subject_ref="meeting:abc:ghi",
        actor="staff",
        owner_words="prefers evening calls",
    )
    assert await shared_memory.brief(business_db, scope, conv.customer_id)
    await brain_erase.erase_customer(business_db, scope, conv.customer_id)
    assert not (await shared_memory.brief(business_db, scope, conv.customer_id)).get("records")
    await pi.close()


async def test_the_proposal_gets_the_block_only_in_brain_mode(api, business_db, monkeypatch):
    from types import SimpleNamespace

    from test_pi_meeting_data import workspace as meeting_workspace

    from app.modules.pi_saas import proposal_writer

    pi, conv, scope = await meeting_workspace(api, business_db, "355000001")

    async def fake_brief(*_a, **_k):
        return {"records": [{"text": "x"}]}

    monkeypatch.setattr(proposal_writer.shared_memory, "brief", fake_brief)
    lead = SimpleNamespace(
        conversation_id=None, customer_id=conv.customer_id, title="Shop", requirements={}
    )
    plain = await proposal_writer.gather(business_db, scope, lead)
    assert proposal_writer.shared_memory.KEY not in plain  # not in brain mode: unchanged
    response = await api.patch(
        "/api/v1/pi/settings/response_rules", json={"value": {"pi_mode": "brain"}}
    )
    assert response.status_code == 200, response.text
    business_db.expire_all()
    brain = await proposal_writer.gather(business_db, scope, lead)
    assert proposal_writer.shared_memory.KEY in brain
    await pi.close()
