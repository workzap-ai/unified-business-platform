"""WhatsApp campaigns: consented audience only, approved template, plan gate, send-time
re-checks (STOP, cancel), quiet hours, results; plus reminder consent and quiet hours."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from pi_saas_support import FakeProvider, configure, worker_ctx
from sqlalchemy import select
from test_pi_saas import _account, _kapso, _message_event, _ready_business, _run_jobs

from app.modules.pi.followups import quiet_until
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi_saas.campaigns import quiet_now, sweep_campaigns
from app.modules.pi_saas.models import PiCustomerConsent, PiSubscription

pytestmark = pytest.mark.integration

APPROVED = {
    "name": "eid_offer",
    "language": "en",
    "status": "APPROVED",
    "components": [{"type": "BODY", "text": "Eid Mubarak! New suits are in store this week."}],
}
CAMPAIGN = {
    "name": "Eid collection",
    "template_name": "eid_offer",
    "template_language": "en",
    "quiet_start": 0,
    "quiet_end": 0,  # quiet hours off for a deterministic test
}


@pytest.fixture
def app(api):
    return api._transport.app  # type: ignore[attr-defined]


@pytest.fixture
def provider(app):
    fake = FakeProvider()
    fake.queue = configure(app, fake)  # type: ignore[attr-defined]
    return fake


async def _customer(db, sender: str) -> UUID:
    conversation = await db.scalar(
        select(PiConversation).where(PiConversation.contact_wa_id == sender)
    )
    assert conversation is not None and conversation.customer_id is not None
    return conversation.customer_id


def _template_sends(provider) -> list[dict]:
    return [
        json.loads(r.content)
        for r in provider.requests
        if r.method == "POST"
        and r.url.path.endswith("/messages")
        and json.loads(r.content).get("type") == "template"
    ]


async def test_campaign_reaches_only_consented_customers_and_rechecks_at_send(
    app, provider, business_db
):
    client, view = await _ready_business(app, provider, business_db, "Noor", "4444444444")
    senders = ["923001111111", "923002222222", "923003333333"]
    for i, sender in enumerate(senders):
        await _kapso(
            client,
            "whatsapp.message.received",
            _message_event("4444444444", sender, "Salam, suits ka rate?", f"wamid.c{i}"),
        )
    await _run_jobs(app, provider, business_db)
    first, second, _third = [await _customer(business_db, s) for s in senders]
    # These enquiries were handed to the team (no AI in tests) two days ago; the chats
    # are quiet now, so offers may go out. A chat active in the last day is left alone.
    for conversation in await business_db.scalars(select(PiConversation)):
        conversation.last_message_at = datetime.now(UTC) - timedelta(days=2)
    await business_db.flush()

    # Nobody has agreed yet.
    base = "/api/v1/pi-app/pi"
    audience = (await client.get(f"{base}/campaigns/audience")).json()
    assert audience["count"] == 0 and audience["whatsapp_connected"] is True
    no_evidence = await client.put(
        f"{base}/customers/{first}/consent", json={"purpose": "marketing", "granted": True}
    )
    assert no_evidence.status_code == 422  # opt-in needs a source
    for customer in (first, second):
        agreed = await client.put(
            f"{base}/customers/{customer}/consent",
            json={"purpose": "marketing", "granted": True, "source": "Signed up at the counter"},
        )
        assert agreed.status_code == 200, agreed.text
    assert (await client.get(f"{base}/campaigns/audience")).json()["count"] == 2

    created = await client.post(f"{base}/campaigns", json=CAMPAIGN)
    assert created.status_code == 201, created.text
    campaign = created.json()["id"]
    # Plan gate, then template approval, are checked before anything is sent.
    account = await _account(business_db, view)
    subscription = await business_db.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == account.tenant_id)
    )
    subscription.plan_key = "starter"
    await business_db.flush()
    gated = await client.post(f"{base}/campaigns/{campaign}/schedule", json={})
    assert gated.status_code == 402 and gated.json()["error"]["code"] == "PLAN_FEATURE_REQUIRED"
    subscription.plan_key = "growth"
    await business_db.flush()
    unapproved = await client.post(f"{base}/campaigns/{campaign}/schedule", json={})
    assert unapproved.json()["error"]["code"] == "REMINDER_TEMPLATE_NOT_APPROVED"
    provider.templates.append(APPROVED)
    check = await client.post(
        f"{base}/whatsapp/templates/check", json={"name": "eid_offer", "language": "en"}
    )
    assert check.json() == {"approved": True, "body": APPROVED["components"][0]["text"]}
    scheduled = await client.post(f"{base}/campaigns/{campaign}/schedule", json={})
    assert scheduled.status_code == 200 and scheduled.json()["status"] == "scheduled"

    ctx = {**worker_ctx(app, business_db), "queue": provider.queue}
    await sweep_campaigns(ctx)
    queued = [job for job in provider.queue.jobs if job[0] == "send_pi_message"]
    assert len(queued) == 2
    # The second customer replies STOP before their message goes out.
    await _kapso(
        client,
        "whatsapp.message.received",
        _message_event("4444444444", senders[1], "STOP", "wamid.stop"),
    )
    held = [job for job in provider.queue.jobs if job[0] == "send_pi_message"]
    provider.queue.jobs = [job for job in provider.queue.jobs if job not in held]
    await _run_jobs(app, provider, business_db)  # the STOP is fully processed first
    provider.queue.jobs = held
    before = len(_template_sends(provider))
    await _run_jobs(app, provider, business_db)
    sends = _template_sends(provider)[before:]
    assert [s["to"] for s in sends] == [senders[0]]
    assert sends[0]["template"] == {"name": "eid_offer", "language": {"code": "en"}}
    consent = await business_db.scalar(
        select(PiCustomerConsent).where(
            PiCustomerConsent.customer_id == second, PiCustomerConsent.purpose == "marketing"
        )
    )
    assert consent.status == "withdrawn" and "STOP" in consent.source

    result = (await client.get(f"{base}/campaigns/{campaign}")).json()
    assert result["status"] == "completed"
    stats = result["results"]
    assert stats["recipients"] == 2 and stats["sent"] == 1 and stats["skipped"] == 1
    assert stats["skipped_reasons"] == {"OPTED_OUT": 1}
    campaign_messages = list(
        await business_db.scalars(
            select(PiMessage).where(PiMessage.idempotency_key.like(f"pi-campaign:{campaign}:%"))
        )
    )
    assert len(campaign_messages) == 2  # never duplicated by a second sweep
    await sweep_campaigns(ctx)
    assert (
        len(
            list(
                await business_db.scalars(
                    select(PiMessage).where(
                        PiMessage.idempotency_key.like(f"pi-campaign:{campaign}:%")
                    )
                )
            )
        )
        == 2
    )
    await client.aclose()


async def test_cancelled_and_viewer_rules(app, provider, business_db):
    client, view = await _ready_business(app, provider, business_db, "Hira", "5555555555")
    await _kapso(
        client,
        "whatsapp.message.received",
        _message_event("5555555555", "923004444444", "Hi", "wamid.v1"),
    )
    await _run_jobs(app, provider, business_db)
    customer = await _customer(business_db, "923004444444")
    base = "/api/v1/pi-app/pi"
    await client.put(
        f"{base}/customers/{customer}/consent",
        json={"purpose": "marketing", "granted": True, "source": "Asked for offers on WhatsApp"},
    )
    account = await _account(business_db, view)
    subscription = await business_db.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == account.tenant_id)
    )
    subscription.plan_key = "business"
    provider.templates.append(APPROVED)
    await business_db.flush()
    campaign = (await client.post(f"{base}/campaigns", json=CAMPAIGN)).json()["id"]
    await client.post(f"{base}/campaigns/{campaign}/schedule", json={})
    cancelled = await client.post(f"{base}/campaigns/{campaign}/cancel")
    assert cancelled.json()["status"] == "cancelled"
    ctx = {**worker_ctx(app, business_db), "queue": provider.queue}
    await sweep_campaigns(ctx)
    assert not [job for job in provider.queue.jobs if job[0] == "send_pi_message"]
    edit = await client.put(f"{base}/campaigns/{campaign}", json=CAMPAIGN)
    assert edit.status_code == 409
    await client.aclose()


def test_quiet_hours_windows():
    night = SimpleNamespace(quiet_start=21, quiet_end=9)
    at = datetime(2026, 9, 30, 17, 0, tzinfo=UTC)  # 22:00 in Karachi (UTC+5)
    assert quiet_now(night, "Asia/Karachi", at) is True
    assert quiet_now(night, "Asia/Karachi", datetime(2026, 9, 30, 6, 0, tzinfo=UTC)) is False
    assert quiet_now(SimpleNamespace(quiet_start=0, quiet_end=0), "UTC", at) is False
    lunch = SimpleNamespace(quiet_start=13, quiet_end=14)
    assert quiet_now(lunch, "UTC", datetime(2026, 9, 30, 13, 30, tzinfo=UTC)) is True
    # Reminders wait for 09:00 local time.
    morning = quiet_until("Asia/Karachi", now=at)
    assert morning == datetime(2026, 10, 1, 4, 0, tzinfo=UTC)
    early = datetime(2026, 9, 30, 1, 0, tzinfo=UTC)  # 06:00 Karachi -> wait until 09:00
    assert quiet_until("Asia/Karachi", now=early) == datetime(2026, 9, 30, 4, 0, tzinfo=UTC)
    assert quiet_until("Asia/Karachi", now=datetime(2026, 9, 30, 6, 0, tzinfo=UTC)) is None
    assert quiet_until("UTC", 0, 0, now=at) is None


async def test_campaigns_stop_at_the_monthly_message_allowance(app, provider, business_db):
    from app.modules.pi_saas.entitlement import meter
    from app.modules.pi_saas.models import PiPlan

    client, view = await _ready_business(app, provider, business_db, "Cap", "8888888888")
    await _kapso(
        client,
        "whatsapp.message.received",
        _message_event("8888888888", "923006660001", "Hi", "wamid.cap1"),
    )
    await _run_jobs(app, provider, business_db)
    customer = await _customer(business_db, "923006660001")
    for conversation in await business_db.scalars(select(PiConversation)):
        conversation.last_message_at = datetime.now(UTC) - timedelta(days=2)
    base = "/api/v1/pi-app/pi"
    await client.put(
        f"{base}/customers/{customer}/consent",
        json={"purpose": "marketing", "granted": True, "source": "Joined our offers list"},
    )
    account = await _account(business_db, view)
    subscription = await business_db.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == account.tenant_id)
    )
    subscription.plan_key = "growth"
    plan = await business_db.scalar(select(PiPlan).where(PiPlan.key == "growth"))
    provider.templates.append(APPROVED)
    await business_db.flush()
    campaign = (await client.post(f"{base}/campaigns", json=CAMPAIGN)).json()["id"]
    assert (await client.post(f"{base}/campaigns/{campaign}/schedule", json={})).status_code == 200
    # The month's message allowance is already used up.
    await meter(
        business_db,
        account.tenant_id,
        account.production_environment_id,
        "messages_out",
        int(plan.allowances["messages"]),
    )
    ctx = {**worker_ctx(app, business_db), "queue": provider.queue}
    await sweep_campaigns(ctx)
    assert not [job for job in provider.queue.jobs if job[0] == "send_pi_message"]
    result = (await client.get(f"{base}/campaigns/{campaign}")).json()
    assert result["status"] == "sending" and result["results"]["waiting"] == 1
    await client.aclose()


async def test_bulk_template_send_queues_checks_sends_a_few_and_keeps_history(
    app, provider, business_db, monkeypatch
):
    from app.modules.pi_saas import template_sends

    monkeypatch.setattr(template_sends, "quiet_now", lambda *a, **k: False)
    client, _view = await _ready_business(app, provider, business_db, "Bulk Co", "4545454545")
    base = "/api/v1/pi-app/pi/whatsapp/templates"
    provider.templates.append(
        {
            "id": "777001",
            "name": "nori_welcome_en",
            "language": "en_US",
            "status": "APPROVED",
            "category": "UTILITY",
            "components": [{"type": "BODY", "text": "Hello {{1}}, welcome to nori."}],
        }
    )
    rows = [
        {"phone": "+92 300 1111111", "person": "Ayesha", "values": ["Ayesha"]},
        {
            "phone": "0300-2222222",
            "person": "Bilal",
            "values": ["Bilal"],
        },  # written locally, no country code
        {"phone": "923003333333", "person": "Chand", "values": ["Chand"]},
        {"phone": "923003333333", "person": "Chand again", "values": ["Chand"]},  # listed twice
        {"phone": "923004444444", "person": "Dana", "values": []},  # a value is missing
        {"phone": "not a number", "values": ["x"]},
    ]
    body = {"name": "nori_welcome_en", "language": "en_US", "rows": rows, "source": "paste"}
    # consent is required, with a note saying how they agreed
    assert (await client.post(f"{base}/batches", json=body)).status_code == 422
    assert (
        await client.post(f"{base}/batches", json={**body, "consent": True, "consent_note": ""})
    ).status_code == 422
    made = await client.post(
        f"{base}/batches",
        json={**body, "consent": True, "consent_note": "Signed up on the nori site"},
    )
    assert made.status_code == 201, made.text
    result = made.json()
    assert result["queued"] == 2 and result["daily_cap"] == 200
    reasons = {r["phone"]: r["reason"] for r in result["rejected"]}
    assert reasons["923003333333"] == "Listed twice"
    assert reasons["0300-2222222"].startswith("Add the country code")
    assert reasons["923004444444"].startswith("Needs 1 value")
    assert provider.sent_messages == []  # queueing sends nothing

    queued = (await client.get(f"{base}/sends")).json()["items"]
    assert sorted(i["status"] for i in queued) == ["queued", "queued"]

    ctx = {**worker_ctx(app, business_db), "queue": provider.queue}
    await template_sends.sweep_template_sends(ctx)
    await _run_jobs(app, provider, business_db)
    sends = _template_sends(provider)
    assert sorted(s["to"] for s in sends) == ["923001111111", "923003333333"]
    assert sends[0]["template"]["components"][0]["parameters"][0]["text"] in {"Ayesha", "Chand"}
    history = (await client.get(f"{base}/sends")).json()["items"]
    assert {i["phone"] for i in history} == {"923001111111", "923003333333"}
    assert all(i["status"] in {"sent", "delivered"} for i in history)
    assert all(i["conversation_id"] for i in history)  # the reply will land in the inbox
    assert (
        len((await client.get(f"{base}/sends", params={"phone": "1111111"})).json()["items"]) == 1
    )
    await template_sends.sweep_template_sends(ctx)  # a second sweep sends nothing again
    await _run_jobs(app, provider, business_db)
    assert len(_template_sends(provider)) == 2
    await client.aclose()


async def test_bulk_template_send_skips_opted_out_cancels_and_respects_the_daily_cap(
    app, provider, business_db, monkeypatch
):
    from app.modules.pi_saas import template_sends

    monkeypatch.setattr(template_sends, "quiet_now", lambda *a, **k: False)
    client, _view = await _ready_business(app, provider, business_db, "Cap Co", "4646464646")
    base = "/api/v1/pi-app/pi/whatsapp/templates"
    provider.templates.append(
        {
            "id": "777002",
            "name": "plain_hello",
            "language": "en_US",
            "status": "APPROVED",
            "category": "UTILITY",
            "components": [{"type": "BODY", "text": "Hello from Workzap."}],
        }
    )
    await _kapso(
        client,
        "whatsapp.message.received",
        _message_event("4646464646", "923005550001", "Salam", "wamid.oo1"),
    )
    await _run_jobs(app, provider, business_db)
    customer = await _customer(business_db, "923005550001")
    stopped = await client.put(
        f"/api/v1/pi-app/pi/customers/{customer}/consent",
        json={"purpose": "marketing", "granted": False, "source": "Said stop"},
    )
    assert stopped.status_code == 200, stopped.text
    rows = [{"phone": "923005550001", "values": []}, {"phone": "923005550002", "values": []}]
    made = await client.post(
        f"{base}/batches",
        json={
            "name": "plain_hello",
            "language": "en_US",
            "rows": rows,
            "consent": True,
            "consent_note": "Asked us on the phone",
        },
    )
    assert made.status_code == 201, made.text
    assert made.json()["queued"] == 1
    assert made.json()["rejected"][0]["reason"].startswith("Withdrew consent")

    # cancel before anything goes out
    batch = made.json()["batch_id"]
    cancelled = await client.post(f"{base}/batches/{batch}/cancel")
    assert cancelled.json() == {"cancelled": 1}
    ctx = {**worker_ctx(app, business_db), "queue": provider.queue}
    await template_sends.sweep_template_sends(ctx)
    assert _template_sends(provider) == []
    items = (await client.get(f"{base}/sends", params={"status": "cancelled"})).json()["items"]
    assert len(items) == 1

    # the daily cap: nothing more goes out once it is reached
    monkeypatch.setattr(template_sends, "DAILY_CAP", 1)
    again = await client.post(
        f"{base}/batches",
        json={
            "name": "plain_hello",
            "language": "en_US",
            "rows": [
                {"phone": "923005550010", "values": []},
                {"phone": "923005550011", "values": []},
            ],
            "consent": True,
            "consent_note": "Asked us on the phone",
        },
    )
    assert again.json()["queued"] == 2
    await template_sends.sweep_template_sends(ctx)
    await _run_jobs(app, provider, business_db)
    assert len(_template_sends(provider)) == 1
    await client.aclose()


def test_pasted_lines_become_rows_and_the_quiet_hours_follow_the_business_zone():
    from app.modules.pi_saas import template_sends

    rows = template_sends.parse_pasted(
        "number, name, value\n+92 300 1234567, Ayesha, Mendeez Demo, 20 November\n\n0300 1;Bilal"
    )
    assert rows[0] == {
        "phone": "+92 300 1234567",
        "person": "Ayesha",
        "values": ["Mendeez Demo", "20 November"],
    }
    assert len(rows) == 2  # the header line has no digits and is left out
    night = datetime(2026, 11, 18, 18, 0, tzinfo=UTC)  # 23:00 in Karachi
    noon = datetime(2026, 11, 18, 7, 0, tzinfo=UTC)  # 12:00 in Karachi
    assert template_sends.quiet_now("Asia/Karachi", night) is True
    assert template_sends.quiet_now("Asia/Karachi", noon) is False


async def test_a_number_blocked_after_queueing_is_not_sent_and_values_with_prices_are_refused(
    app, provider, business_db, monkeypatch
):
    from app.modules.pi_saas import template_sends

    monkeypatch.setattr(template_sends, "quiet_now", lambda *a, **k: False)
    client, _view = await _ready_business(app, provider, business_db, "Block Co", "4747474747")
    base = "/api/v1/pi-app/pi/whatsapp/templates"
    provider.templates.append(
        {
            "id": "777003",
            "name": "note_one",
            "language": "en_US",
            "status": "APPROVED",
            "category": "UTILITY",
            "components": [{"type": "BODY", "text": "Hello {{1}}."}],
        }
    )
    made = await client.post(
        f"{base}/batches",
        json={
            "name": "note_one",
            "language": "en_US",
            "rows": [
                {"phone": "923006660001", "values": ["Ayesha"]},
                {"phone": "923006660002", "values": ["Rs 5,000"]},  # a price is never sent here
                {"phone": "923006660003", "values": ["pay to IBAN PK36SCBL0000001123456702"]},
            ],
            "consent": True,
            "consent_note": "Asked us on the phone",
        },
    )
    assert made.status_code == 201, made.text
    assert made.json()["queued"] == 1
    assert len(made.json()["rejected"]) == 2
    # blocked after it was queued: the worker leaves it out
    blocked = await client.post(
        "/api/v1/pi-app/pi/blocklist",
        json={"value": "923006660001", "kind": "number", "reason": "test", "close_chats": False},
    )
    assert blocked.status_code in {200, 201}, blocked.text
    ctx = {**worker_ctx(app, business_db), "queue": provider.queue}
    await template_sends.sweep_template_sends(ctx)
    await _run_jobs(app, provider, business_db)
    assert _template_sends(provider) == []
    items = (await client.get(f"{base}/sends", params={"status": "skipped"})).json()["items"]
    assert [i["error"] for i in items] == ["BLOCKED"]
    # the one-number send obeys the same blocklist
    single = await client.post(
        f"{base}/send",
        json={
            "phone": "923006660001",
            "name": "note_one",
            "language": "en_US",
            "values": ["Ayesha"],
            "consent": True,
        },
    )
    assert single.status_code == 422
    await client.aclose()


def test_value_problem_refuses_prices_and_bank_details_but_not_dates_or_names():
    from app.modules.pi_saas import template_sends

    assert template_sends.value_problem(["Rs 5,000"]) is not None
    assert template_sends.value_problem(["Your payment received"]) is not None
    assert template_sends.value_problem(["03001234567890"]) is not None
    assert template_sends.value_problem(["Mendeez Demo", "20 November 2026"]) is None
