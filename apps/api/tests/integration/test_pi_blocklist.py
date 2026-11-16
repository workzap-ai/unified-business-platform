"""The blocklist on the disposable database: blocking a number or a range, the inbound path
dropping a blocked sender before anything is stored, unblocking, the inbox "block this chat" action,
the suggestions for a bulk-created flood, and that another workspace is never affected. Run only
through scripts/pi-test-env.sh."""

from typing import Any

import httpx
import pytest
from sqlalchemy import func, select, update
from test_pi_pipeline import intent, pi_workspace, scripted_gateway

from app.modules.pi.models import PiConversation, PiMessage, WhatsAppWebhookEvent
from app.modules.pi_saas.blocklist.models import PiBlockedContact

pytestmark = pytest.mark.integration

URL = "/api/v1/pi/blocklist"
FLOOD = "62895636626854"
OTHER = "15550000009"


async def rows(db: Any, tenant: Any, model: Any) -> int:
    return int(
        await db.scalar(select(func.count()).select_from(model).where(model.tenant_id == tenant))
        or 0
    )


async def test_a_blocked_number_is_dropped_before_anything_is_stored(
    api: httpx.AsyncClient, business_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    pi = await pi_workspace(api, business_db)
    calls = scripted_gateway(monkeypatch, lambda text: intent("greeting", 1.0))
    response = await api.post(
        URL, json={"value": f"+{FLOOD}", "reason": "Black image flood", "note": "Indonesia"}
    )
    assert response.status_code == 201, response.text
    assert response.json()["value"] == FLOOD and response.json()["kind"] == "number"

    await pi.process("hello", "wamid.blocked-1", sender=FLOOD)
    await pi.process("hello again", "wamid.blocked-2", sender=FLOOD)

    assert await rows(business_db, pi.tenant_id, PiConversation) == 0  # no chat, no customer row
    assert await rows(business_db, pi.tenant_id, PiMessage) == 0
    assert calls == []  # no model was asked
    events = list(
        await business_db.scalars(
            select(WhatsAppWebhookEvent).where(WhatsAppWebhookEvent.tenant_id == pi.tenant_id)
        )
    )
    assert len(events) == 2 and {e.status for e in events} == {"processed"}
    listed = (await api.get(URL)).json()
    assert listed["active"] == 1 and listed["blocked_messages"] == 2
    assert listed["items"][0]["hits"] == 2 and listed["items"][0]["reason"] == "Black image flood"
    await pi.close()


async def test_another_number_is_still_answered(
    api: httpx.AsyncClient, business_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    pi = await pi_workspace(api, business_db)
    scripted_gateway(monkeypatch, lambda text: intent("greeting", 1.0))
    await api.post(URL, json={"value": FLOOD})
    await pi.process("hello", "wamid.ok-1", sender=OTHER)
    assert await rows(business_db, pi.tenant_id, PiConversation) == 1
    await pi.close()


async def test_a_range_blocks_every_number_that_starts_with_it(
    api: httpx.AsyncClient, business_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    pi = await pi_workspace(api, business_db)
    scripted_gateway(monkeypatch, lambda text: intent("greeting", 1.0))
    response = await api.post(URL, json={"value": "628956366", "kind": "prefix"})
    assert response.status_code == 201, response.text
    await pi.process("hi", "wamid.range-1", sender="62895636626001")
    await pi.process("hi", "wamid.range-2", sender="62895636613999")
    assert await rows(business_db, pi.tenant_id, PiConversation) == 0
    await pi.process("hi", "wamid.range-3", sender="62895637000000")  # a different range
    assert await rows(business_db, pi.tenant_id, PiConversation) == 1
    await pi.close()


async def test_a_whole_country_cannot_be_blocked(api: httpx.AsyncClient, business_db: Any) -> None:
    await pi_workspace(api, business_db)
    response = await api.post(URL, json={"value": "+62", "kind": "prefix"})
    assert response.status_code >= 400, response.text
    assert (await api.get(URL)).json()["items"] == []


async def test_unblocking_answers_the_number_again_and_keeps_the_record(
    api: httpx.AsyncClient, business_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    pi = await pi_workspace(api, business_db)
    scripted_gateway(monkeypatch, lambda text: intent("greeting", 1.0))
    created = (await api.post(URL, json={"value": FLOOD})).json()
    await pi.process("hi", "wamid.un-1", sender=FLOOD)
    assert await rows(business_db, pi.tenant_id, PiConversation) == 0
    response = await api.delete(f"{URL}/{created['id']}")
    assert response.status_code == 200 and response.json()["active"] is False
    await pi.process("hi", "wamid.un-2", sender=FLOOD)
    assert await rows(business_db, pi.tenant_id, PiConversation) == 1
    listed = (await api.get(URL)).json()
    assert listed["active"] == 0 and len(listed["items"]) == 1 and listed["items"][0]["hits"] == 1
    again = await api.post(URL, json={"value": FLOOD})  # blocking it again switches it back on
    assert again.status_code == 201 and (await api.get(URL)).json()["active"] == 1
    assert await rows(business_db, pi.tenant_id, PiBlockedContact) == 1
    await pi.close()


async def test_blocking_a_chat_from_the_inbox_closes_it(
    api: httpx.AsyncClient, business_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    pi = await pi_workspace(api, business_db)
    scripted_gateway(monkeypatch, lambda text: intent("greeting", 1.0))
    await pi.process("hi", "wamid.chat-1", sender=FLOOD)
    chat = await pi.conversation()
    response = await api.post(f"{URL}/from-conversation/{chat.id}", json={"reason": "Spam"})
    assert response.status_code == 201, response.text
    assert response.json()["value"] == FLOOD and response.json()["closed_chats"] == 1
    await business_db.refresh(chat)
    assert chat.status == "closed" and chat.unread_count == 0
    await pi.process("hi", "wamid.chat-2", sender=FLOOD)
    assert await rows(business_db, pi.tenant_id, PiMessage) >= 1  # the old record stays
    messages_before = await rows(business_db, pi.tenant_id, PiMessage)
    await pi.process("hi", "wamid.chat-3", sender=FLOOD)
    assert await rows(business_db, pi.tenant_id, PiMessage) == messages_before
    await pi.close()


async def test_bulk_block_counts_and_skips_bad_numbers(
    api: httpx.AsyncClient, business_db: Any
) -> None:
    await pi_workspace(api, business_db)
    response = await api.post(
        f"{URL}/bulk",
        json={
            "values": ["62895636626001", "+62 895636626002", "62895636626001", "123"],
            "reason": "Flood",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["added"] == 2 and body["already_listed"] == 0 and len(body["skipped"]) == 1
    assert (await api.get(URL)).json()["active"] == 2


async def test_suggestions_find_a_range_that_only_ever_sent_media(
    api: httpx.AsyncClient, business_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    pi = await pi_workspace(api, business_db)
    scripted_gateway(monkeypatch, lambda text: intent("greeting", 1.0))
    for n in range(4):
        await pi.process("hi", f"wamid.s-{n}", sender=f"6289563662680{n}")
    # Four chats that wrote text are not a media flood.
    assert (await api.get(f"{URL}/suggestions")).json()["ranges"] == []
    await business_db.execute(
        update(PiMessage)
        .where(PiMessage.tenant_id == pi.tenant_id, PiMessage.direction == "inbound")
        .values(message_type="image")
    )
    await business_db.commit()
    ranges = (await api.get(f"{URL}/suggestions")).json()["ranges"]
    assert [(r["prefix"], r["chats"]) for r in ranges] == [("628956366", 4)]
    await api.post(URL, json={"value": "628956366", "kind": "prefix"})
    assert (await api.get(f"{URL}/suggestions")).json()["ranges"] == []  # already blocked
    await pi.close()


async def test_a_workspace_never_sees_or_feels_another_workspaces_blocklist(
    api: httpx.AsyncClient, business_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = await pi_workspace(api, business_db)
    await api.post(URL, json={"value": FLOOD})
    await first.close()
    second = await pi_workspace(api, business_db, number="987654321")
    assert (await api.get(URL)).json()["items"] == []
    scripted_gateway(monkeypatch, lambda text: intent("greeting", 1.0))
    await second.process("hi", "wamid.iso-1", sender=FLOOD)
    assert await rows(business_db, second.tenant_id, PiConversation) == 1
    await second.close()
