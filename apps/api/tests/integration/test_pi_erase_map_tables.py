"""Platform spec X5 and ST12: "delete my data" also removes the map (every version), the Solution
Boxes with their move history, the offer log, the profile facts and snapshots, the move log and the
open items, and reports what was removed and what is kept. One assertion per table."""

import pytest
from sqlalchemy import func, select
from test_pi_pipeline import pi_workspace
from test_pi_staff_review import scoped, seed

from app.modules.pi import business_profile, business_profile_store
from app.modules.pi.box_models import PiBoxTransition, PiMapVersion, PiOfferLog, PiSolutionBox
from app.modules.pi.business_profile_models import (
    PiBusinessProfile,
    PiPageSnapshot,
    PiProfileFact,
)
from app.modules.pi.open_item_models import PiOpenItem
from app.modules.pi.problem_models import PiProblem, PiProblemLink
from app.modules.pi.think_models import PiHypothesis, PiMoveLog
from app.shared.scope import WorkspaceScope

pytestmark = pytest.mark.integration


async def count(db, model):
    db.expire_all()
    return int(await db.scalar(select(func.count()).select_from(model)) or 0)


async def seeded(api, db):
    pi = await pi_workspace(api, db)
    conversation = await seed(pi, db)
    where = scoped(conversation)
    customer = conversation.customer_id
    version = await db.scalar(select(PiMapVersion).where(PiMapVersion.version == 2))
    parent = await db.scalar(select(PiSolutionBox))
    child = PiSolutionBox(
        **where,
        customer_id=customer,
        state="collecting",
        version=2,
        parent_box_id=parent.id,
        map_version_id=version.id,
    )
    db.add(child)
    await db.flush()
    db.add_all(
        [
            PiBoxTransition(
                **where,
                box_id=parent.id,
                from_state="collecting",
                to_state="ready",
                actor="pi",
            ),
            PiBoxTransition(
                **where,
                box_id=child.id,
                from_state="collecting",
                to_state="ready",
                actor="pi",
            ),
            PiOpenItem(
                **where,
                conversation_id=conversation.id,
                customer_id=customer,
                kind="owner_question",
                key="q:1",
                text="what does it cost",
            ),
        ]
    )
    scope = WorkspaceScope.system(
        conversation.tenant_id, conversation.environment_id, frozenset(), "test"
    )
    profile = business_profile.new_profile()
    business_profile.add_fact(profile, "business_name", "Ata Clothing", "owner")
    look = {
        "status": "ok",
        "url": "https://ata.pk",
        "content_hash": "abc",
        "title": "Ata",
        "description": "Clothes",
    }
    await business_profile_store.persist(db, scope, customer, profile, look)
    await db.flush()
    return pi, conversation


async def test_erasing_a_customer_removes_the_map_boxes_log_profile_and_open_items(
    api, business_db
):
    pi, conversation = await seeded(api, business_db)
    customer_id = conversation.customer_id
    tables = (
        PiMapVersion,
        PiSolutionBox,
        PiBoxTransition,
        PiOfferLog,
        PiProfileFact,
        PiPageSnapshot,
        PiBusinessProfile,
        PiMoveLog,
        PiHypothesis,
        PiOpenItem,
        PiProblem,
        PiProblemLink,
    )
    for model in tables:
        assert await count(business_db, model) > 0, model.__tablename__

    refused = await api.post(f"/api/v1/pi/brain-erasure/{customer_id}", json={})
    assert refused.status_code == 422
    assert await count(business_db, PiMapVersion) == 2  # nothing happens without confirm

    done = await api.post(f"/api/v1/pi/brain-erasure/{customer_id}", json={"confirm": True})
    assert done.status_code == 200, done.text
    result = done.json()
    removed = result["removed"]
    assert removed["map_versions"] == 2
    assert removed["solution_boxes"] == 2
    assert removed["box_transitions"] == 2
    assert removed["offer_log"] == 2
    assert removed["business_profiles"] == 1
    assert removed["move_log"] == 2
    assert removed["open_items"] == 1
    # what is kept is reported, with the reason
    assert result["kept"] == {"documents": 0, "payments": 0}
    assert {"documents", "payments", "customer_contact"} <= set(result["kept_reasons"])

    for model in tables:
        assert await count(business_db, model) == 0, model.__tablename__
    await pi.close()


async def test_another_customers_map_and_boxes_are_not_touched(api, business_db):
    pi, conversation = await seeded(api, business_db)
    where = scoped(conversation)
    customer_id = conversation.customer_id
    from app.modules.customers.models import Customer

    other = Customer(**where, name="Other owner")
    business_db.add(other)
    await business_db.flush()
    business_db.add_all(
        [
            PiMapVersion(**where, customer_id=other.id, version=1, map_json={}),
            PiSolutionBox(**where, customer_id=other.id, state="collecting"),
        ]
    )
    await business_db.flush()
    done = await api.post(f"/api/v1/pi/brain-erasure/{customer_id}", json={"confirm": True})
    assert done.status_code == 200, done.text
    assert await count(business_db, PiMapVersion) == 1
    assert await count(business_db, PiSolutionBox) == 1
    await pi.close()
