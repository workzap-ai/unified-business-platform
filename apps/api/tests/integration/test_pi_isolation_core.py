"""Two workspaces, the same phone number as a customer of both: the durable surfaces that make pi
remember an owner never cross a workspace or a customer (FT-E2a).

Surfaces: durable memory (memory_block), the business profile (business_profile_store), closed slots
and their carry into a new chat (slot_carry), the problem book (problems.noted_context, ProblemBook)
and the map (map_builder). Each surface has a CONTROL where the owning workspace sees its data, then
leak checks: the other workspace asking about its own customer, and the other workspace asking with
the owner's customer id (a wrong-scope read must find nothing)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from test_pi_brain_problems import adaptive, say
from test_pi_learning_loop import model
from test_pi_pipeline import pi_workspace

from app.modules.customers.models import Customer
from app.modules.pi import business_profile_store, map_builder, memory_block, problems, slot_carry
from app.modules.pi.box_models import PiMapVersion
from app.modules.pi.models import PiConversation, PiMemory
from app.modules.pi.problem_models import PiProblem, PiProblemLink

pytestmark = pytest.mark.integration

PHONE = "15550000001"  # the same owner texts both workspaces
BUSINESS_A = "Acme Stock Traders"
SLOTS_A = [{"slot": "shops.where", "q": "Which shop is it in Karachi?"}]
TITLE_A1, TITLE_A2 = "Acme best-sellers run out", "Acme suppliers deliver late"
TITLE_B = "Beta invoices are paid slowly"


async def brain(api):
    from test_pi_brain_problems import brain_on

    await brain_on(api)


async def two_chats(api, db, monkeypatch):
    """Workspace A and workspace B, the same phone number chatting with both."""
    adaptive(monkeypatch, model)
    a = await pi_workspace(api, db, business_type="service_business")
    await brain(api)
    await say(a, "hello", "iso-a")
    b = await pi_workspace(api, db, business_type="service_business", number="987654321")
    await brain(api)
    await b.process("hello", "iso-b", sender=PHONE)
    await b.deliver_all()
    assert a.tenant_id != b.tenant_id
    conv_a, conv_b = await a.conversation(), await b.conversation()
    await db.refresh(conv_a)
    await db.refresh(conv_b)
    return SimpleNamespace(
        a=a,
        b=b,
        conv_a=conv_a,
        conv_b=conv_b,
        scope_a=a.scope(),
        scope_b=b.scope(),
        cust_a=conv_a.customer_id,
        cust_b=conv_b.customer_id,
    )


async def test_the_same_phone_is_two_separate_customers_and_chats(api, business_db, monkeypatch):
    w = await two_chats(api, business_db, monkeypatch)
    rows = list(
        await business_db.scalars(select(Customer).where(Customer.id.in_([w.cust_a, w.cust_b])))
    )
    assert len(rows) == 2 and w.cust_a != w.cust_b
    assert {r.tenant_id for r in rows} == {w.conv_a.tenant_id, w.conv_b.tenant_id}
    assert {r.whatsapp_id or r.phone for r in rows} and len(
        {(r.whatsapp_id or r.phone or "").lstrip("+") for r in rows}
    ) == 1  # one number, two records
    assert w.conv_a.id != w.conv_b.id
    assert w.conv_a.contact_wa_id == w.conv_b.contact_wa_id
    await w.a.close()
    await w.b.close()


async def test_durable_memory_stays_with_its_workspace(api, business_db, monkeypatch):
    db = business_db
    w = await two_chats(api, db, monkeypatch)
    cust_a = await db.get(Customer, w.cust_a)
    cust_b = await db.get(Customer, w.cust_b)
    changed = await memory_block.refresh(
        db,
        w.scope_a,
        w.conv_a,
        profile={"business_name": BUSINESS_A, "location": "Karachi"},
        language="ur",
        voice_note=False,
        message_id=None,
    )
    await db.flush()
    assert "business_name" in changed
    own = await memory_block.load(db, w.scope_a, w.conv_a, cust_a)
    assert own.facts.get("business_name") == BUSINESS_A  # control
    assert own.prefs.get("language") == "ur"
    # leak 1: the other workspace's chat with the same phone knows nothing
    other = await memory_block.load(db, w.scope_b, w.conv_b, cust_b)
    assert other.facts == {} and other.prefs == {}
    # leak 2: the other workspace's scope with the owner's own conversation finds nothing
    wrong = await memory_block.load(db, w.scope_b, w.conv_a, cust_a)
    assert wrong.facts == {} and wrong.prefs == {}
    # the rows themselves: none under B's tenant
    count_b = await db.scalar(
        select(func.count()).select_from(PiMemory).where(PiMemory.tenant_id == w.conv_b.tenant_id)
    )
    assert count_b == 0
    # B writing its own memory does not touch or read A's
    await memory_block.refresh(
        db,
        w.scope_b,
        w.conv_b,
        profile={"business_name": "Beta Billing"},
        language=None,
        voice_note=False,
        message_id=None,
    )
    await db.flush()
    again = await memory_block.load(db, w.scope_a, w.conv_a, cust_a)
    assert again.facts.get("business_name") == BUSINESS_A
    assert (await memory_block.load(db, w.scope_b, w.conv_b, cust_b)).facts[
        "business_name"
    ] == "Beta Billing"
    await w.a.close()
    await w.b.close()


async def test_the_business_profile_stays_with_its_workspace(api, business_db, monkeypatch):
    db = business_db
    w = await two_chats(api, db, monkeypatch)
    stored = await business_profile_store.persist(
        db,
        w.scope_a,
        w.cust_a,
        {
            "facts": [
                {
                    "key": "what_they_do",
                    "value": "wholesale of mobile accessories",
                    "source": "owner",
                    "confirmed": True,
                }
            ]
        },
    )
    assert stored is not None
    profile = await business_profile_store.find(db, w.scope_a, w.cust_a)
    assert profile is not None and profile.id == stored.id  # control
    rows = await business_profile_store.facts_of(db, w.scope_a, profile.id)
    assert [r.value for r in rows] == ["wholesale of mobile accessories"]
    loaded = await business_profile_store.load_dict(db, w.scope_a, w.cust_a)
    assert loaded is not None and loaded["facts"]
    context: dict = {}
    await business_profile_store.sync_context(db, w.scope_a, w.conv_a, context)
    assert "accessories" in context.get(
        "profile_grounding", ""
    )  # control: it grounds the idea filter
    # leaks: the other workspace, with its own customer and with the owner's customer id
    assert await business_profile_store.find(db, w.scope_b, w.cust_b) is None
    assert await business_profile_store.find(db, w.scope_b, w.cust_a) is None
    assert await business_profile_store.facts_of(db, w.scope_b, profile.id) == []
    assert await business_profile_store.load_dict(db, w.scope_b, w.cust_a) is None
    for conversation in (w.conv_b, w.conv_a):
        brief_before = dict(conversation.service_brief or {})
        context_b: dict = {}
        await business_profile_store.sync_context(db, w.scope_b, conversation, context_b)
        assert "profile_grounding" not in context_b
        assert dict(conversation.service_brief or {}) == brief_before
    await w.a.close()
    await w.b.close()


async def earlier_chat(db, conversation, brief, age_days=1):
    """A closed earlier chat of the same customer, with this brief."""
    db.add(
        PiConversation(
            tenant_id=conversation.tenant_id,
            environment_id=conversation.environment_id,
            customer_id=conversation.customer_id,
            connection_id=conversation.connection_id,
            contact_wa_id=conversation.contact_wa_id,
            status="closed",
            last_message_at=datetime.now(UTC) - timedelta(days=age_days),
            service_brief=brief,
        )
    )
    await db.flush()


async def test_closed_slots_are_carried_only_inside_the_same_customer_and_workspace(
    api, business_db, monkeypatch
):
    db = business_db
    w = await two_chats(api, db, monkeypatch)
    await earlier_chat(db, w.conv_a, {"closed_slots": SLOTS_A, "asked_facts": ["business_name"]})
    for conversation in (w.conv_a, w.conv_b):
        conversation.service_brief = {}
    await db.flush()
    # leak 1: B's chat with the same phone, run first, receives nothing of A's
    assert await slot_carry.carry_into(db, w.scope_b, w.conv_b) is False
    assert "closed_slots" not in (w.conv_b.service_brief or {})
    assert "asked_facts" not in (w.conv_b.service_brief or {})
    # leak 2: the owner's conversation read under B's scope finds nothing either
    w.conv_a.service_brief = {}
    assert await slot_carry.carry_into(db, w.scope_b, w.conv_a) is False
    assert "closed_slots" not in (w.conv_a.service_brief or {})
    # control: the owner's own workspace does get the copy
    w.conv_a.service_brief = {}
    assert await slot_carry.carry_into(db, w.scope_a, w.conv_a) is True
    carried = w.conv_a.service_brief["closed_slots"]
    assert [c["q"] for c in carried] == [SLOTS_A[0]["q"]]
    assert w.conv_a.service_brief["asked_facts"] == ["business_name"]
    # and B still holds nothing after A's copy was made
    w.conv_b.service_brief = {}
    assert await slot_carry.carry_into(db, w.scope_b, w.conv_b) is False
    await w.a.close()
    await w.b.close()


def problem(scope, customer_id, number, title):
    return PiProblem(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        customer_id=customer_id,
        number=number,
        title=title,
        title_local=title,
        category="stock_inventory",
        status="confirmed",
    )


async def noted(db, w):
    first, second = (
        problem(w.scope_a, w.cust_a, 1, TITLE_A1),
        problem(w.scope_a, w.cust_a, 2, TITLE_A2),
    )
    theirs = problem(w.scope_b, w.cust_b, 1, TITLE_B)  # the same number, another workspace
    db.add_all([first, second, theirs])
    await db.flush()
    db.add(
        PiProblemLink(
            tenant_id=w.scope_a.tenant_id,
            environment_id=w.scope_a.environment_id,
            from_id=first.id,
            to_id=second.id,
            type="causes",
            evidence="owner_said",
            confidence=Decimal("0.9"),
        )
    )
    await db.flush()
    return first, second, theirs


async def test_the_problem_book_stays_with_its_workspace_and_customer(
    api, business_db, monkeypatch
):
    db = business_db
    w = await two_chats(api, db, monkeypatch)
    await noted(db, w)
    titles = lambda items: {i.get("title") for i in items}  # noqa: E731
    own = await problems.noted_context(db, w.scope_a, w.cust_a)
    assert {TITLE_A1, TITLE_A2} <= titles(own)  # control
    assert TITLE_B not in titles(own)
    mine = await problems.ProblemBook(db, w.scope_a, w.cust_a, "en").active()
    assert {p.title for p in mine} == {TITLE_A1, TITLE_A2}
    # leaks: B's own customer sees only B's problem; the owner's id under B's scope sees nothing
    theirs = await problems.noted_context(db, w.scope_b, w.cust_b)
    assert titles(theirs) == {TITLE_B}
    assert await problems.noted_context(db, w.scope_b, w.cust_a) == []
    assert await problems.ProblemBook(db, w.scope_b, w.cust_a, "en").active() == []
    assert [
        p.title for p in await problems.ProblemBook(db, w.scope_b, w.cust_b, "en").active()
    ] == [TITLE_B]
    # and A's id with the wrong customer inside A's workspace shows nothing (another customer)
    assert await problems.noted_context(db, w.scope_a, w.cust_b) == []
    await w.a.close()
    await w.b.close()


async def test_the_map_stays_with_its_workspace_and_customer(api, business_db, monkeypatch):
    db = business_db
    w = await two_chats(api, db, monkeypatch)
    await noted(db, w)
    row, stored = await map_builder.save_if_changed(db, w.scope_a, w.cust_a)
    assert stored and row is not None  # control: the owner's map is drawn
    drawn = [n.get("label", "") + n.get("title", "") for n in row.map_json["nodes"]]
    assert len(drawn) == 2 and any("Acme" in text for text in drawn)
    assert (await map_builder.latest_version(db, w.scope_a, w.cust_a)).id == row.id
    # leaks: the owner's id under B's scope draws nothing and stores nothing
    assert await map_builder.current_inputs(db, w.scope_b, w.cust_a) == ([], [])
    assert await map_builder.save_if_changed(db, w.scope_b, w.cust_a) == (None, False)
    assert await map_builder.latest_version(db, w.scope_b, w.cust_a) is None
    # B's own customer gets B's map only
    theirs, theirs_stored = await map_builder.save_if_changed(db, w.scope_b, w.cust_b)
    assert theirs_stored and theirs is not None
    text = str(theirs.map_json)
    assert "Beta" in text and "Acme" not in text
    assert "Beta" not in str(row.map_json)
    versions = list(await db.scalars(select(PiMapVersion)))
    assert {(v.tenant_id, v.customer_id) for v in versions} == {
        (w.conv_a.tenant_id, w.cust_a),
        (w.conv_b.tenant_id, w.cust_b),
    }
    assert await map_builder.versions(db, w.scope_b, w.cust_a) == []
    await w.a.close()
    await w.b.close()
