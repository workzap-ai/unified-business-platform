"""Platform spec v1.4, Part 16 (16.3, OT11, OT13, OT15): the Business Profile on tables.

The warm-up writes through to `pi_business_profiles`, `pi_profile_facts` and `pi_page_snapshots`;
the dashboard routes read, correct, confirm and delete facts; what is stored wins on the next turn;
only confirmed facts ground ideas (G2); erasing a customer removes the profile. Real database and
webhook flow; the AI and WhatsApp are mocked."""

from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_pi_brain_problems import say
from test_pi_warmup_flow import warm_chat

from app.modules.pi import business_profile, business_profile_store, idea_filter
from app.modules.pi.business_profile_models import (
    PiBusinessProfile,
    PiPageSnapshot,
    PiProfileFact,
)

pytestmark = pytest.mark.integration

API = "/api/v1/pi/business-profiles"


def scope_of(conversation):
    return SimpleNamespace(
        tenant_id=conversation.tenant_id, environment_id=conversation.environment_id
    )


async def warmed(api, db, monkeypatch):
    pi = await warm_chat(api, db, monkeypatch)
    await say(pi, "Hi", "p-1")
    await say(pi, "mera clothing brand hai, baby aur male clothes", "p-2")
    await say(pi, "website nahi hai", "p-3")
    conversation = await pi.conversation()
    await db.refresh(conversation)
    return pi, conversation


async def listed(api):
    response = await api.get(API)
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def test_the_warmup_profile_is_kept_in_tables_with_source_and_flags(
    api, business_db, monkeypatch
):
    pi, conversation = await warmed(api, business_db, monkeypatch)
    profile = await business_profile_store.find(
        business_db, scope_of(conversation), conversation.customer_id
    )
    assert profile is not None
    rows = {
        r.key: r
        for r in await business_profile_store.facts_of(
            business_db, scope_of(conversation), profile.id
        )
    }
    assert rows["what_they_do"].source == "owner" and rows["what_they_do"].confirmed is True
    assert rows["what_they_do"].confirmed_at is not None
    assert rows["website"].value == "none"
    assert profile.digital_flags == {"website": "none"}  # "none" is a fact, not a problem
    assert "clothing" in profile.what_they_do
    items = await listed(api)
    assert items[0]["facts"] and items[0]["customer_name"]
    await pi.close()


async def test_a_page_fact_is_provisional_and_the_snapshot_keeps_no_page_text(
    api, business_db, monkeypatch
):
    pi, conversation = await warmed(api, business_db, monkeypatch)
    scope = scope_of(conversation)
    page = business_profile.new_profile()
    business_profile.add_fact(
        page, "business_name", "Ata Clothing", "page", evidence="Ata | Home", url="https://ata.pk"
    )
    business_profile.add_fact(page, "online_orders", "yes", "page", url="https://ata.pk")
    look = {
        "status": "ok",
        "url": "https://ata.pk",
        "content_hash": "abc123",
        "title": "Ata | Home",
        "description": "Clothes",
        "text": "THE WHOLE PAGE MUST NOT BE KEPT",
    }
    merged = await business_profile_store.load_dict(business_db, scope, conversation.customer_id)
    merged["facts"] += page["facts"]
    await business_profile_store.persist(business_db, scope, conversation.customer_id, merged, look)
    profile = await business_profile_store.find(business_db, scope, conversation.customer_id)
    rows = {r.key: r for r in await business_profile_store.facts_of(business_db, scope, profile.id)}
    assert rows["business_name"].source == "page" and rows["business_name"].confirmed is False
    assert rows["business_name"].evidence_snippet == "Ata | Home"
    assert rows["business_name"].fetched_at is not None
    snaps = list(await business_db.scalars(select(PiPageSnapshot)))
    assert len(snaps) == 1 and snaps[0].content_hash == "abc123"
    assert "text" not in snaps[0].extracted
    assert "WHOLE PAGE" not in str(snaps[0].extracted)
    # OT13: only the owner's confirmed facts ground ideas
    grounded = business_profile_store.grounding_text(list(rows.values()))
    assert "Ata Clothing" not in grounded and "online_orders" not in grounded
    await pi.close()


async def test_the_dashboard_can_confirm_edit_and_delete_a_fact(api, business_db, monkeypatch):
    pi, conversation = await warmed(api, business_db, monkeypatch)
    scope = scope_of(conversation)
    page = business_profile.new_profile()
    business_profile.add_fact(page, "business_name", "Ata Clothing", "page", url="https://ata.pk")
    business_profile.add_fact(page, "places", "Lahore", "page")
    await business_profile_store.persist(business_db, scope, conversation.customer_id, page)
    profile = (await listed(api))[0]
    facts = {f["key"]: f for f in profile["facts"]}
    assert facts["business_name"]["confirmed"] is False

    confirm = await api.post(f"{API}/{profile['id']}/facts/{facts['business_name']['id']}/confirm")
    assert confirm.status_code == 200 and confirm.json()["confirmed"] is True

    edit = await api.patch(
        f"{API}/{profile['id']}/facts/{facts['places']['id']}",
        json={"value": "Gulberg, Lahore. Call +92 300 1234567 or ali@ata.pk"},
    )
    assert edit.status_code == 200, edit.text
    body = edit.json()
    assert body["source"] == "owner" and body["confirmed"] is True
    assert "1234567" not in body["value"] and "@" not in body["value"]  # OT15
    assert "Gulberg" in body["value"]
    only_contact = await api.patch(
        f"{API}/{profile['id']}/facts/{facts['places']['id']}", json={"value": "ali@ata.pk"}
    )
    assert only_contact.status_code == 422

    again = (await listed(api))[0]
    assert again["city_area"].startswith("Gulberg")  # the summary follows the facts
    gone = await api.delete(f"{API}/{profile['id']}/facts/{facts['business_name']['id']}")
    assert gone.status_code == 200
    after = (await listed(api))[0]
    assert "business_name" not in {f["key"] for f in after["facts"]}
    missing = await api.delete(f"{API}/{profile['id']}/facts/{facts['business_name']['id']}")
    assert missing.status_code == 404
    await pi.close()


async def test_what_is_stored_wins_on_the_next_turn_and_confirmed_facts_ground_ideas(
    api, business_db, monkeypatch
):
    pi, conversation = await warmed(api, business_db, monkeypatch)
    scope = scope_of(conversation)
    page = business_profile.new_profile()
    business_profile.add_fact(page, "online_orders", "yes", "page", url="https://ata.pk")
    await business_profile_store.persist(business_db, scope, conversation.customer_id, page)
    context: dict = {}
    await business_profile_store.sync_context(business_db, scope, conversation, context)
    assert "profile_grounding" in context  # the owner's own facts count
    assert "online_orders" not in context["profile_grounding"]  # a page fact is provisional

    profile = (await listed(api))[0]
    fact = next(f for f in profile["facts"] if f["key"] == "online_orders")
    await api.post(f"{API}/{profile['id']}/facts/{fact['id']}/confirm")
    await api.delete(
        f"{API}/{profile['id']}/facts/"
        + next(f["id"] for f in profile["facts"] if f["key"] == "website")
    )
    context = {}
    await business_profile_store.sync_context(business_db, scope, conversation, context)
    assert "online_orders yes" in context["profile_grounding"]
    brief = {f["key"] for f in conversation.service_brief["business_profile"]["facts"]}
    assert "website" not in brief  # the deleted fact is gone from the brief too

    idea = "Show the old sets in your online store first."
    ctx = idea_filter.with_grounding(None, context["profile_grounding"])
    assert idea_filter.failures(idea, "kapre bik nahi rahe") == ["G2"]
    assert idea_filter.failures(idea, "kapre bik nahi rahe", ctx) == []
    await pi.close()


async def test_a_persist_failure_never_breaks_the_turn(api, business_db, monkeypatch):
    pi, conversation = await warmed(api, business_db, monkeypatch)
    bad = {"facts": [{"key": "what_they_do", "value": "x", "source": "owner", "confirmed": True}]}
    # a customer that does not exist: the foreign key refuses, the savepoint rolls back, no raise
    result = await business_profile_store.persist(
        business_db, scope_of(conversation), conversation.id, bad
    )
    assert result is None
    assert await business_db.scalar(select(PiBusinessProfile.id).limit(1)) is not None
    await pi.close()


async def test_erasing_a_customer_removes_the_profile(api, business_db, monkeypatch):
    pi, conversation = await warmed(api, business_db, monkeypatch)
    response = await api.post(
        f"/api/v1/pi/brain-erasure/{conversation.customer_id}", json={"confirm": True}
    )
    assert response.status_code == 200, response.text
    assert response.json()["removed"]["business_profiles"] == 1
    assert await business_db.scalar(select(PiProfileFact.id).limit(1)) is None
    assert await business_db.scalar(select(PiBusinessProfile.id).limit(1)) is None
    await pi.close()
