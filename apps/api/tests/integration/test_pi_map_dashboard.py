# ruff: noqa: F811
"""The problem map on the PI Customer dashboard: versions stored only when the map changed, the
edits the owner can make, the Solution Box card, and that one customer never sees another's."""

import json
from decimal import Decimal
from uuid import uuid4

import pytest
from pi_saas_support import pi_client
from sqlalchemy import func, select
from test_pi_customer_portal import (  # noqa: F401  (app and provider are fixtures)
    CUSTOMER,
    NUMBER,
    PORTAL,
    _business_with_chat,
    _sign_in,
    app,
    provider,
)
from test_pi_saas import _kapso, _message_event, _run_jobs

from app.modules.pi import map_builder
from app.modules.pi.box_models import PiMapVersion, PiSolutionBox
from app.modules.pi.brain_docs_models import PiBrainDocument
from app.modules.pi.models import PiConversation
from app.modules.pi.problem_models import PiProblem, PiProblemLink, PiProblemRevision
from app.modules.pi_customer.access import CSRF_COOKIE
from app.shared.scope import WorkspaceScope

pytestmark = pytest.mark.integration


def scope_of(conversation):
    return WorkspaceScope.system(
        conversation.tenant_id, conversation.environment_id, frozenset(), "test"
    )


async def note(db, conversation, number, local, **extra):
    row = PiProblem(
        tenant_id=conversation.tenant_id,
        environment_id=conversation.environment_id,
        customer_id=conversation.customer_id,
        number=number,
        title=extra.pop("title", f"Problem {number}"),
        title_local=local,
        category=extra.pop("category", "stock_inventory"),
        status=extra.pop("status", "confirmed"),
        **extra,
    )
    db.add(row)
    await db.flush()
    return row


async def join(db, conversation, a, b, kind="causes", evidence="owner_said"):
    db.add(
        PiProblemLink(
            tenant_id=conversation.tenant_id,
            environment_id=conversation.environment_id,
            from_id=a.id,
            to_id=b.id,
            type=kind,
            evidence=evidence,
            confidence=Decimal("0.9"),
        )
    )
    await db.flush()


async def conversations_of(db):
    return list(await db.scalars(select(PiConversation).order_by(PiConversation.created_at)))


def csrf(client):
    return {"x-csrf-token": client.cookies[CSRF_COOKIE]}


async def second_customer(app, provider, business, db):
    await _kapso(
        business,
        "whatsapp.message.received",
        _message_event(NUMBER, "15550007002", "Hello", "wamid.p-other-map"),
    )
    await _run_jobs(app, provider, db)
    first, second = await conversations_of(db)
    assert first.customer_id != second.customer_id
    return first, second


async def test_a_version_is_stored_only_when_the_map_changed(
    app, provider, business_db, monkeypatch
):
    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    [conversation] = await conversations_of(business_db)
    scope, who = scope_of(conversation), conversation.customer_id
    assert await map_builder.save_if_changed(business_db, scope, who) == (None, False)
    stock = await note(business_db, conversation, 1, "purana maal ruka hai")
    cash = await note(business_db, conversation, 2, "paisa phansa", category="cash_collections")
    v1, changed = await map_builder.save_if_changed(business_db, scope, who)
    assert changed and v1.version == 1
    again, changed = await map_builder.save_if_changed(business_db, scope, who)
    assert not changed and again.id == v1.id
    await join(business_db, conversation, stock, cash)
    v2, changed = await map_builder.save_if_changed(business_db, scope, who)
    assert changed and v2.version == 2 and len(v2.map_json["links"]) == 1
    third = await note(business_db, conversation, 3, "suppliers late")
    v3, changed = await map_builder.save_if_changed(business_db, scope, who)
    assert changed and v3.version == 3
    assert [n["is_new"] for n in v3.map_json["nodes"]] == [False, False, True]
    third.status = "resolved"
    v4, changed = await map_builder.save_if_changed(business_db, scope, who)
    assert changed and v4.map_json["nodes"][2]["status"] == "resolved"
    assert not (await map_builder.save_if_changed(business_db, scope, who))[1]
    await business.aclose()


async def test_versions_of_two_customers_and_two_businesses_never_mix(
    app, provider, business_db, monkeypatch
):
    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    first, second = await second_customer(app, provider, business, business_db)
    await note(business_db, first, 1, "alpha problem")
    await note(business_db, second, 1, "beta problem")
    await note(business_db, second, 2, "beta other")
    a, _ = await map_builder.save_if_changed(business_db, scope_of(first), first.customer_id)
    b, _ = await map_builder.save_if_changed(business_db, scope_of(second), second.customer_id)
    assert [n["label"] for n in a.map_json["nodes"]] == ["alpha problem"]
    assert [n["label"] for n in b.map_json["nodes"]] == ["beta problem", "beta other"]
    assert a.version == 1 and b.version == 1  # each customer counts its own versions
    mine = await map_builder.versions(business_db, scope_of(first), first.customer_id)
    assert [v.id for v in mine] == [a.id]
    # the other customer's id under this business's scope finds nothing of the first's
    crossed = await map_builder.latest_version(business_db, scope_of(first), second.customer_id)
    assert crossed is not None and crossed.id == b.id  # same business, the id picks the customer
    foreign = WorkspaceScope.system(uuid4(), first.environment_id, frozenset(), "t")
    assert await map_builder.latest_version(business_db, foreign, first.customer_id) is None
    assert await map_builder.versions(business_db, foreign, first.customer_id) == []
    other_env = WorkspaceScope.system(first.tenant_id, uuid4(), frozenset(), "t")
    assert await map_builder.versions(business_db, other_env, first.customer_id) == []
    await business.aclose()


async def test_the_dashboard_shows_the_latest_map_and_older_versions(
    app, provider, business_db, monkeypatch
):
    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    customer = await _sign_in(app, provider)
    cid = (await customer.get(f"{PORTAL}/conversations")).json()[0]["id"]
    path = f"{PORTAL}/conversations/{cid}/map"
    empty = (await customer.get(path)).json()
    assert empty["available"] is False and empty["latest"] is None and empty["versions"] == []
    [conversation] = await conversations_of(business_db)
    stock = await note(business_db, conversation, 1, "purana maal ruka hai")
    cash = await note(business_db, conversation, 2, "paisa phansa")
    await join(business_db, conversation, stock, cash)
    first = (await customer.get(path)).json()
    assert first["available"] and first["latest"]["version"] == 1
    assert [n["label"] for n in first["latest"]["map"]["nodes"]] == [
        "purana maal ruka hai",
        "paisa phansa",
    ]
    assert (await customer.get(path)).json()["latest"]["version"] == 1  # no change, no version
    await note(business_db, conversation, 3, "suppliers late")
    second = (await customer.get(path)).json()
    assert second["latest"]["version"] == 2
    assert [v["version"] for v in second["versions"]] == [2, 1]
    assert second["versions"][0]["problems"] == 3 and second["versions"][1]["problems"] == 2
    old = (await customer.get(f"{path}/1")).json()
    assert old["version"] == 1 and len(old["map"]["nodes"]) == 2
    assert (await customer.get(f"{path}/9")).status_code == 404
    assert (await customer.get(f"{path}/x")).status_code == 422
    await business.aclose()
    await customer.aclose()


async def test_customer_a_can_never_read_customer_bs_map_or_box(
    app, provider, business_db, monkeypatch
):
    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    mine, theirs = await second_customer(app, provider, business, business_db)
    assert mine.contact_wa_id == CUSTOMER
    await note(business_db, theirs, 1, "bs secret cash trouble")
    await map_builder.save_if_changed(business_db, scope_of(theirs), theirs.customer_id)
    business_db.add(
        PiSolutionBox(
            tenant_id=theirs.tenant_id,
            environment_id=theirs.environment_id,
            customer_id=theirs.customer_id,
            state="offered",
        )
    )
    await business_db.flush()
    a = await _sign_in(app, provider)
    for suffix in ("map", "map/1", "box"):
        found = await a.get(f"{PORTAL}/conversations/{theirs.id}/{suffix}")
        assert found.status_code == 404, suffix
    edit = await a.post(
        f"{PORTAL}/conversations/{theirs.id}/map/problems/P1",
        json={"action": "resolve"},
        headers=csrf(a),
    )
    assert edit.status_code == 404
    own = (await a.get(f"{PORTAL}/conversations/{mine.id}/map")).json()
    assert own["available"] is False and "secret" not in json.dumps(own)
    assert (await a.get(f"{PORTAL}/conversations/{mine.id}/box")).json()["available"] is False
    anonymous = pi_client(app)
    assert (await anonymous.get(f"{PORTAL}/conversations/{mine.id}/map")).status_code == 401
    await anonymous.aclose()
    await business.aclose()
    await a.aclose()


async def test_the_owner_edits_the_map_like_in_chat(app, provider, business_db, monkeypatch):
    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    customer = await _sign_in(app, provider)
    cid = (await customer.get(f"{PORTAL}/conversations")).json()[0]["id"]
    [conversation] = await conversations_of(business_db)
    stock = await note(business_db, conversation, 1, "purana maal ruka hai")
    await note(business_db, conversation, 2, "paisa phansa")
    path = f"{PORTAL}/conversations/{cid}/map"
    edit = f"{path}/problems/P1"
    assert (await customer.post(edit, json={"action": "resolve"})).status_code == 403  # no CSRF
    await customer.get(path)
    done = await customer.post(edit, json={"action": "resolve"}, headers=csrf(customer))
    assert done.status_code == 200
    body = done.json()
    assert body["latest"]["version"] == 2
    assert body["latest"]["map"]["nodes"][0]["status"] == "resolved"
    await business_db.refresh(stock)
    assert stock.status == "resolved" and stock.revision == 2
    again = await customer.post(edit, json={"action": "resolve"}, headers=csrf(customer))
    assert again.json()["latest"]["version"] == 2  # nothing changed, no new version
    parked = await customer.post(
        f"{path}/problems/P2", json={"action": "park"}, headers=csrf(customer)
    )
    assert parked.json()["latest"]["map"]["nodes"][1]["status"] == "parked"
    renamed = await customer.post(
        f"{path}/problems/P2",
        json={"action": "rename", "label": "maal mein paisa phansa 0300 1234567"},
        headers=csrf(customer),
    )
    node = renamed.json()["latest"]["map"]["nodes"][1]
    assert node["label"].startswith("maal mein paisa") and "1234567" not in node["label"]
    reopened = await customer.post(edit, json={"action": "reopen"}, headers=csrf(customer))
    assert reopened.json()["latest"]["map"]["nodes"][0]["status"] == "open"
    reasons = list(
        await business_db.scalars(
            select(PiProblemRevision.reason).where(PiProblemRevision.by == "person")
        )
    )
    assert sorted(reasons) == ["parked", "renamed", "reopened", "resolved"]
    blank = await customer.post(
        edit, json={"action": "rename", "label": " "}, headers=csrf(customer)
    )
    assert blank.status_code == 422
    for wrong in ({"action": "delete"}, {"action": "park", "extra": 1}):
        refused = await customer.post(edit, json=wrong, headers=csrf(customer))
        assert refused.status_code == 422
    for target in ("P99", "xyz"):
        missing = await customer.post(
            f"{path}/problems/{target}", json={"action": "park"}, headers=csrf(customer)
        )
        assert missing.status_code == 404
    assert await business_db.scalar(select(func.count()).select_from(PiMapVersion)) == 5
    await business.aclose()
    await customer.aclose()


async def test_the_box_card_shows_state_and_document_status_but_never_an_amount(
    app, provider, business_db, monkeypatch
):
    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    customer = await _sign_in(app, provider)
    cid = (await customer.get(f"{PORTAL}/conversations")).json()[0]["id"]
    [conversation] = await conversations_of(business_db)
    path = f"{PORTAL}/conversations/{cid}/box"
    assert (await customer.get(path)).json()["available"] is False
    await note(business_db, conversation, 1, "purana maal ruka hai")
    await customer.get(f"{PORTAL}/conversations/{cid}/map")
    collecting = (await customer.get(path)).json()
    assert collecting["state"] == "collecting" and collecting["document"] is None
    assert collecting["map_version"] == 1
    business_db.add(
        PiSolutionBox(
            tenant_id=conversation.tenant_id,
            environment_id=conversation.environment_id,
            customer_id=conversation.customer_id,
            state="sent",
            version=1,
        )
    )
    business_db.add(
        PiBrainDocument(
            tenant_id=conversation.tenant_id,
            environment_id=conversation.environment_id,
            customer_id=conversation.customer_id,
            offer_id=uuid4(),
            kind="solution",
            number=1,
            status="sent",
            total=Decimal("123456.00"),
            currency="PKR",
            content={"secret": "section 4"},
        )
    )
    await business_db.flush()
    sent = (await customer.get(path)).json()
    assert sent["state"] == "sent" and sent["document"]["sent"] is True
    assert sent["document"]["ref"] == "SD-0001"
    flat = json.dumps(sent)
    assert "123456" not in flat and "PKR" not in flat and "section 4" not in flat
    await business.aclose()
    await customer.aclose()
