"""pi drafts a pack for an unknown trade; people approve it; it goes live only after shadowing
(spec 8.5 job 5, 8.6)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, workspace
from test_pi_learning_loop import learning_on
from test_pi_service_conversations import turn

from app.modules.pi import learning_nightly, learning_packs
from app.modules.pi.learning_models import PiLearnedPack
from app.modules.pi.models import PiConversation

pytestmark = pytest.mark.integration
L = "/api/v1/pi/brain-learning"


def asks(context, n):
    return turn(reply="Noted. Which items run out first?", language="en")


async def five_falconers(pi, db):
    for n in range(5):
        await pi.process("I sell hoods and jesses for falconry", f"lp-{n}", sender=f"1555000010{n}")
    rows = list(await db.scalars(select(PiConversation)))
    for row in rows:
        row.service_brief = {
            **(row.service_brief or {}),
            "customer_profile": {"business_type": "falconry"},
        }
    await db.flush()
    return rows


def writer_for(draft):
    async def write(evidence):
        write.seen = evidence
        return draft

    return lambda scope: write


def good_draft():
    return learning_packs.PackDraft(
        name="Falconry equipment suppliers",
        signals=["hood", "jess", "mews", "lure", "telemetry", "bird feed"],
        vocabulary={"Mews": "where the birds are housed"},
        questions={"stock": ["Which items run out first?"]},
        problems=[learning_packs.PackProblem(category="stock_inventory", phrase="feed runs out")],
        care=["model wrote this"],
        scope_rule="model wrote this too",
    )


async def test_five_unknown_businesses_get_a_draft_that_waits_for_people(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, asks)
    pi = await workspace(api, business_db)
    await learning_on(api)
    await five_falconers(pi, business_db)
    scope = pi.scope()
    result = await learning_packs.draft_new(business_db, scope, writer_for(good_draft())(scope))
    assert result["drafted"] == 1
    [pack] = (await business_db.scalars(select(PiLearnedPack))).all()
    assert pack.status == "draft" and pack.care_approved is False
    assert pack.evidence["businesses"] == 5
    assert await learning_packs.live_brief(business_db, scope, "hoods and jesses") == ""
    # Once a week at most, and the same cluster is not drafted twice.
    again = await learning_packs.draft_new(business_db, scope, writer_for(good_draft())(scope))
    assert again["drafted"] == 0
    await pi.close()


async def test_a_pack_needs_listening_approval_care_approval_and_a_shadow_run(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, asks)
    pi = await workspace(api, business_db)
    await five_falconers(pi, business_db)
    scope = pi.scope()
    await learning_packs.draft_new(business_db, scope, writer_for(good_draft())(scope))
    [pack] = (await business_db.scalars(select(PiLearnedPack))).all()

    # Care cannot be skipped: shadowing alone never makes a pack live.
    approved = await api.post(f"{L}/packs/{pack.id}/approve-listening")
    assert approved.json()["status"] == "shadow"
    refused = await api.post(
        f"{L}/packs/{pack.id}/approve-care", json={"care": ["x"], "scope_rule": ""}
    )
    assert refused.status_code == 422
    for _ in range(20):  # twenty conversations it would have recognised
        await learning_packs.note_shadow(business_db, scope, uuid4(), "hoods and jesses")
    await business_db.flush()
    assert await learning_packs.promote_shadows(business_db, scope) == 0  # no care approval yet
    care = await api.post(
        f"{L}/packs/{pack.id}/approve-care",
        json={
            "care": ["Never give animal welfare advice"],
            "scope_rule": "Notes how the shop runs.",
        },
    )
    assert care.json()["care_approved"] is True
    assert care.json()["content"]["care"] == [
        "Never give animal welfare advice"
    ]  # the person's text
    await business_db.flush()
    assert (
        await learning_packs.promote_shadows(
            business_db, scope, datetime.now(UTC) + timedelta(days=1)
        )
        == 1
    )
    await business_db.refresh(pack)
    assert pack.status == "live"
    brief = await learning_packs.live_brief(business_db, scope, "I sell hoods and jesses")
    assert "Falconry equipment suppliers" in brief and "Which items run out first?" in brief
    assert await learning_packs.live_brief(business_db, scope, "I sell shoes") == ""
    await pi.close()


async def test_the_nightly_run_drafts_but_never_publishes(api, business_db, monkeypatch):
    adaptive(monkeypatch, asks)
    pi = await workspace(api, business_db)
    await learning_on(api)
    await five_falconers(pi, business_db)
    from app.modules.pi.configuration import settings_row

    settings = await settings_row(business_db, pi.scope())
    run = await learning_nightly.run_workspace(
        business_db, settings, pack_writer=writer_for(good_draft())
    )
    assert run.digest["packs"]["drafted"] == 1 and run.digest["packs"]["went_live"] == 0
    [pack] = (await business_db.scalars(select(PiLearnedPack))).all()
    assert pack.status == "draft"
    await pi.close()
