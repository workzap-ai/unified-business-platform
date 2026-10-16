"""Team alerts on WhatsApp: team members' numbers on the team board, and pi telling a
person on WhatsApp when a card is given to them or due within the hour, by WhatsApp's
rules (free text inside their 24-hour window, else an approved template, else nothing
but the in-app notification). Only saved numbers are ever messaged, once per alert."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from test_pi_pipeline import Pi, pi_workspace
from test_service_lifecycle import create

from app.modules.customers.models import Customer
from app.modules.notifications.models import Notification
from app.modules.pi.models import PiConversation, WhatsAppConnection
from app.modules.pi_saas import team_alerts

pytestmark = pytest.mark.integration

BOARD = "/api/v1/pi/team-board"
STAFF = "923001234567"


async def _teammate(pi: Pi, name: str = "Bilal Ahmed") -> str:
    role = await create(
        pi.api,
        "roles",
        {
            "key": f"board-{uuid4().hex[:8]}",
            "name": "Board member",
            "permissions": ["pi.work.read"],
        },
    )
    member = await create(
        pi.api,
        "members",
        {
            "email": f"staff-{uuid4().hex}@example.com",
            "display_name": name,
            "role_ids": [role["id"]],
        },
    )
    return str(member["user_id"])


async def _staff_chat(pi: Pi, number: str, *, hours_ago: float) -> None:
    """``number`` messaged the business's WhatsApp number ``hours_ago``."""
    scope = {"tenant_id": UUID(pi.tenant_id), "environment_id": UUID(pi.environment_id)}
    connection = await pi.db.scalar(
        select(WhatsAppConnection).where(WhatsAppConnection.tenant_id == UUID(pi.tenant_id))
    )
    customer = Customer(**scope, name="Bilal (team)", phone=f"+{number}")
    pi.db.add(customer)
    await pi.db.flush()
    when = datetime.now(UTC) - timedelta(hours=hours_ago)
    pi.db.add(
        PiConversation(
            **scope,
            customer_id=customer.id,
            connection_id=connection.id,
            contact_wa_id=number,
            last_message_at=when,
            last_inbound_at=when,
        )
    )
    await pi.db.flush()


async def _alerts(pi: Pi) -> list[str]:
    """Run the queued alert jobs as the worker would; returns what each did."""
    jobs = [args for name, args in pi.app.state.queue.jobs if name == "send_team_alert"]
    pi.app.state.queue.jobs.clear()
    return [await team_alerts.send_team_alert(pi.ctx, *args) for args in jobs]


async def _numbers(pi: Pi, **body: Any) -> dict:
    response = await pi.api.put(f"{BOARD}/members", json=body)
    assert response.status_code == 200, response.text
    return response.json()


async def _task(pi: Pi, assignee: str, **extra: Any) -> dict:
    made = await pi.api.post(
        f"{BOARD}/tasks",
        json={"title": "Call the printer about the banner", "assignee_user_id": assignee, **extra},
    )
    assert made.status_code == 201, made.text
    return made.json()


async def _notes(pi: Pi, kind: str, user_id: str) -> int:
    return int(
        await pi.db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.tenant_id == UUID(pi.tenant_id),
                Notification.kind == kind,
                Notification.recipient_user_id == UUID(user_id),
            )
        )
        or 0
    )


async def test_members_numbers_are_saved_and_checked(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    mate = await _teammate(pi)
    view = (await api.get(f"{BOARD}/members")).json()
    assert view["enabled"] is True and view["business_number"] == "+15551234567"
    assert {m["id"]: m["whatsapp"] for m in view["members"]}[mate] == ""

    view = await _numbers(pi, numbers={mate: "+92 300-1234567"})
    [saved] = [m for m in view["members"] if m["id"] == mate]
    assert saved["whatsapp"] == STAFF and saved["window_open"] is False

    owner = next(m["id"] for m in view["members"] if m["id"] != mate)
    for bad, code in (
        ({mate: "12345"}, "PHONE_INVALID"),
        ({str(uuid4()): "923001112223"}, "MEMBER_UNKNOWN"),
        ({owner: STAFF}, "PHONE_DUPLICATE"),
        ({mate: "+1 555 123 4567"}, "PHONE_IS_BUSINESS"),
    ):
        response = await api.put(f"{BOARD}/members", json={"numbers": bad})
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == code
    bad_template = await api.put(
        f"{BOARD}/members", json={"template_name": "Task Assigned!", "template_language": "en"}
    )
    assert bad_template.status_code == 422

    # Saved in the existing settings JSON: the generic pi settings still round-trip.
    settings = await api.get("/api/v1/pi/settings")
    assert settings.status_code == 200, settings.text
    assert settings.json()["whatsapp_config"]["team_alerts"]["numbers"] == {mate: STAFF}

    # An empty value removes the number.
    view = await _numbers(pi, numbers={mate: ""})
    assert {m["id"]: m["whatsapp"] for m in view["members"]}[mate] == ""
    await pi.close()


async def test_assigning_a_card_tells_the_person_on_whatsapp_inside_their_window(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    mate = await _teammate(pi)
    await _numbers(pi, numbers={mate: STAFF})
    await _staff_chat(pi, STAFF, hours_ago=2)
    due = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    card = await _task(pi, mate, due_at=due.isoformat())

    assert await _alerts(pi) == ["sent"]
    [message] = pi.sent
    assert message["to"] == STAFF and message["type"] == "text"
    body = message["text"]["body"]
    assert body.startswith("pi: Service Owner gave you a task: Call the printer about the banner")
    assert " · due " in body and body.endswith("/pi/team")
    assert await _notes(pi, "pi.task.assigned", mate) == 1

    # Once per card and person: given away and back again, no second WhatsApp.
    me = (await api.get(BOARD)).json()["me"]
    for who in (me, mate):
        moved = await api.patch(f"{BOARD}/tasks/{card['id']}", json={"assignee_user_id": who})
        assert moved.status_code == 200, moved.text
    assert await _alerts(pi) == ["duplicate"]
    assert len(pi.sent) == 1

    # The board filters by member and counts their cards.
    board = (await api.get(BOARD, params={"who": mate})).json()
    assert [c["id"] for c in board["columns"]["todo"]] == [card["id"]]
    assert board["by_member"] == {mate: 1}
    assert (await api.get(BOARD, params={"who": "nobody"})).status_code == 422

    # Switched off: nobody hears on WhatsApp.
    await _numbers(pi, enabled=False)
    other = await _task(pi, mate)
    assert other["assignee"]["id"] == mate
    assert await _alerts(pi) == ["off"]
    assert len(pi.sent) == 1
    await pi.close()


async def test_outside_the_window_only_a_template_goes_or_nothing(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    mate = await _teammate(pi)
    await _numbers(pi, numbers={mate: STAFF})
    await _staff_chat(pi, STAFF, hours_ago=30)

    # No template: no WhatsApp, the in-app notification only.
    await _task(pi, mate)
    assert await _alerts(pi) == ["no_window"]
    assert pi.sent == []
    assert await _notes(pi, "pi.task.assigned", mate) == 1

    # With an approved template: that goes out, with the name, task and due time.
    await _numbers(pi, template_name="task_assigned", template_language="en")
    due = datetime.now(UTC) + timedelta(days=1)
    await _task(pi, mate, title="Send the logo files", due_at=due.isoformat())
    assert await _alerts(pi) == ["template"]
    [message] = pi.sent
    assert message["to"] == STAFF and message["type"] == "template"
    assert message["template"]["name"] == "task_assigned"
    assert message["template"]["language"] == {"code": "en"}
    values = [p["text"] for p in message["template"]["components"][0]["parameters"]]
    assert values[0] == "Bilal" and values[1] == "Send the logo files"
    assert values[2] == team_alerts.when_text(due, "UTC")
    await pi.close()


async def test_a_card_due_within_the_hour_gets_one_reminder(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    mate = await _teammate(pi)
    await _numbers(pi, numbers={mate: STAFF})
    await _staff_chat(pi, STAFF, hours_ago=1)
    soon = datetime.now(UTC) + timedelta(minutes=40)
    await _task(pi, mate, title="Proof for Crescent Bakers", due_at=soon.isoformat())
    later = datetime.now(UTC) + timedelta(hours=5)
    await _task(pi, mate, title="Not yet", due_at=later.isoformat())
    assert await _alerts(pi) == ["sent", "sent"]
    pi.sent.clear()

    assert await team_alerts.remind_due(pi.ctx) == 1
    assert await team_alerts.remind_due(pi.ctx) == 0
    [message] = pi.sent
    assert message["to"] == STAFF
    assert message["text"]["body"].startswith("pi: Reminder, due ")
    assert "Proof for Crescent Bakers" in message["text"]["body"]
    assert await _notes(pi, "pi.task.due", mate) == 1
    await pi.close()


async def test_a_number_that_was_not_saved_is_never_messaged(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    mate = await _teammate(pi)
    # Their number has an open chat with the business, but it isn't in the setting.
    await _staff_chat(pi, STAFF, hours_ago=1)
    soon = datetime.now(UTC) + timedelta(minutes=30)
    await _task(pi, mate, due_at=soon.isoformat())
    assert await _alerts(pi) == ["no_number"]
    assert await team_alerts.remind_due(pi.ctx) == 0
    assert pi.sent == []
    assert await _notes(pi, "pi.task.assigned", mate) == 1
    assert await _notes(pi, "pi.task.due", mate) == 1

    # Test message: needs a saved number.
    test = await api.post(f"{BOARD}/members/{mate}/test")
    assert test.status_code == 422
    await _numbers(pi, numbers={mate: STAFF})
    test = await api.post(f"{BOARD}/members/{mate}/test")
    assert test.status_code == 200 and test.json()["delivery"] == "sent"
    assert await _alerts(pi) == ["sent"]
    assert [m["to"] for m in pi.sent] == [STAFF]
    await pi.close()


async def test_the_nav_counts_my_open_cards(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    me = (await api.get(BOARD)).json()["me"]
    await _task(pi, me)
    await _task(pi, me, title="Second")
    nav = (await api.get("/api/v1/navigation")).json()

    def find(items: list[dict]) -> dict | None:
        for item in items:
            if item["key"] == "pi-team":
                return item
            found = find(item["children"])
            if found:
                return found
        return None

    team = find([i for s in nav["sections"] for i in s["items"]])
    assert team is not None and team["badge"] == 2
    await pi.close()
