"""The Nori Platform board on the disposable database: nori's signed push (the door), numbers added
by hand, a message from such a number filed by the bridge hook, and the board itself. A fake nori
and a fake WhatsApp provider on httpx mock transports: no network. Run only through
scripts/pi-test-env.sh."""

import time

import pytest
from sqlalchemy import func, select
from test_nori_credits_bridge import bridge

from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi_saas.models import PiTask
from app.modules.pi_saas.nori_board.forward import forward_due
from app.modules.pi_saas.nori_board.models import PiNoriItem
from app.modules.pi_saas.nori_credits.hook import BOARD_ACK
from app.modules.pi_saas.nori_credits.models import PiNoriBridgeLog
from tests.support.fake_nori import SECRET, STRANGER, signed

pytestmark = pytest.mark.integration

BOARD = "/api/v1/pi/team-board"
NUMBERS = "/api/v1/pi/nori-board/numbers"
WRITER = "923007770001"


def push_payload(ref="rq-1", **extra):
    return {
        "ref": ref,
        "kind": "feature",
        "title": "Van sales module",
        "text": "We need van sales in nori",
        "workspace": "Mendeez",
        "person": "Ali",
        "department": "Sales",
        "ts": int(time.time() * 1000),
        **extra,
    }


async def push(b, payload, *, secret=SECRET):
    body, sig = signed(secret, payload)
    return await b.pi.api.post(
        "/api/pi/nori-board",
        content=body,
        headers={"x-workzap-signature": sig, "content-type": "application/json"},
    )


async def cards(b, **params):
    response = await b.pi.api.get(BOARD, params={"kind": "nori", **params})
    assert response.status_code == 200, response.text
    return [c for column in response.json()["columns"].values() for c in column]


async def add_number(b, phone=WRITER, **extra):
    return await b.pi.api.post(
        NUMBERS,
        json={"phone": phone, "workspace": "Mendeez", "person": "Sara", "department": "Stock"}
        | extra,
    )


# --- the door ---


async def outbound_bodies(b):
    return list(
        await b.pi.db.scalars(
            select(PiMessage.body)
            .where(PiMessage.direction == "outbound")
            .order_by(PiMessage.created_at)
        )
    )


async def test_a_registry_chat_stays_open_for_the_team_and_the_brain_stays_silent(api, business_db):
    b = await bridge(api, business_db, board=True)
    await add_number(b)
    await b.say(WRITER, "The stock export is not working", "wamid.chat-1")
    await b.say(WRITER, "Also the till report is empty", "wamid.chat-2")
    # Two messages, two cards, one chat, one acknowledgement, nothing else from pi.
    assert len(await cards(b)) == 2
    assert await outbound_bodies(b) == [BOARD_ACK]
    rows = [(await b.inbound_rows(m))[0] for m in ("wamid.chat-1", "wamid.chat-2")]
    assert rows[0].conversation_id == rows[1].conversation_id
    await b.pi.close()


async def test_a_photo_from_a_registry_number_is_filed_and_the_chat_kept(api, business_db):
    b = await bridge(api, business_db, board=True)
    await add_number(b)
    await b.pi.process("the screen as it looks", "wamid.photo-1", sender=WRITER, kind="image")
    found = await cards(b)
    assert len(found) == 1
    assert "photo" in found[0]["title"] and "the screen as it looks" in found[0]["title"]
    [inbound] = await b.inbound_rows("wamid.photo-1")
    assert (await b.pi.db.get(PiConversation, inbound.conversation_id)).mode == "human"
    assert await outbound_bodies(b) == [BOARD_ACK]
    await b.pi.close()


async def test_a_registry_chat_the_team_gave_back_to_the_ai_goes_to_human_again(api, business_db):
    b = await bridge(api, business_db, board=True)
    await add_number(b)
    await b.say(WRITER, "The stock export is not working", "wamid.back-1")
    [first] = await b.inbound_rows("wamid.back-1")
    conversation = await b.pi.db.get(PiConversation, first.conversation_id)
    conversation.mode = "ai"
    await b.pi.db.commit()
    await b.say(WRITER, "Any news on the export?", "wamid.back-2")
    await b.pi.db.refresh(conversation)
    assert conversation.mode == "human"  # the brain never answers a registry person
    assert (await outbound_bodies(b)).count(BOARD_ACK) == 1  # one acknowledgement per chat
    assert await outbound_bodies(b) == [BOARD_ACK]  # and nothing else from pi
    await b.pi.close()


async def test_door_is_off_until_the_board_flag_is_on(api, business_db):
    b = await bridge(api, business_db)  # enabled, board not set
    response = await push(b, push_payload())
    assert response.status_code == 503
    assert response.json()["reason"] == "disabled"
    await b.pi.close()


async def test_door_files_a_card_and_a_repeat_of_the_ref_is_not_a_second_card(api, business_db):
    b = await bridge(api, business_db, board=True)
    first = await push(b, push_payload(url="https://nori.test/help/requests/1"))
    assert first.status_code == 200, first.text
    assert first.json()["created"] is True
    again = await push(b, push_payload(ts=int(time.time() * 1000) + 5))
    assert again.status_code == 200
    assert again.json() == {"ok": True, "id": first.json()["id"], "created": False}

    found = await cards(b)
    assert len(found) == 1
    card = found[0]
    assert card["kind"] == "nori"
    assert card["title"] == "Van sales module"
    assert card["column"] == "todo"
    assert card["nori"] == {
        "item_kind": "feature",
        "workspace": "Mendeez",
        "person": "Ali",
        "department": "Sales",
        "phone_mask": "",
        "source": "nori",
        "url": "https://nori.test/help/requests/1",
        "conversation_id": None,
    }
    await b.pi.close()


async def test_door_refusals_leave_no_card(api, business_db):
    b = await bridge(api, business_db, board=True)
    bad_sig = await push(b, push_payload(), secret="another-secret-0123456789")
    assert bad_sig.status_code == 401
    assert bad_sig.json()["reason"] == "bad_signature"

    stale = await push(b, push_payload(ts=int(time.time()) - 3600))
    assert stale.status_code == 401 and stale.json()["reason"] == "stale"

    kind = await push(b, push_payload(ref="rq-2", kind="rant"))
    assert kind.status_code == 400 and kind.json()["reason"] == "bad_kind"

    link = await push(b, push_payload(ref="rq-3", url="https://evil.example/x"))
    assert link.status_code == 400 and link.json()["reason"] == "bad_url"

    body, sig = signed(SECRET, push_payload(ref="rq-4"))
    headers = {"x-workzap-signature": sig, "content-type": "application/json"}
    assert (
        await b.pi.api.post("/api/pi/nori-board", content=body, headers=headers)
    ).status_code == 200
    replay = await b.pi.api.post("/api/pi/nori-board", content=body, headers=headers)
    assert replay.status_code == 409 and replay.json()["reason"] == "replay"

    big = await b.pi.api.post(
        "/api/pi/nori-board",
        content=b"{" + b" " * 9000 + b"}",
        headers={"x-workzap-signature": sig, "content-type": "application/json"},
    )
    assert big.status_code == 413

    assert [c["nori"]["workspace"] for c in await cards(b)] == ["Mendeez"]  # only rq-4
    await b.pi.close()


async def test_door_audit_rows_hold_no_text(api, business_db):
    b = await bridge(api, business_db, board=True)
    await push(b, push_payload(phone="+92 300 7770001", text="secret plan"))
    rows = list(
        await b.pi.db.scalars(select(PiNoriBridgeLog).where(PiNoriBridgeLog.kind == "board"))
    )
    assert [r.outcome for r in rows] == ["filed"]
    assert rows[0].recipient_mask and "7770001" not in rows[0].recipient_mask
    assert "secret plan" not in repr([vars(r) for r in rows])
    await b.pi.close()


async def test_door_keeps_the_kill_switch(api, business_db):
    b = await bridge(api, business_db, board=True)
    b.pi.app.state.settings.nori_bridge_kill = True
    assert (await push(b, push_payload())).status_code == 503
    await b.pi.close()


# --- numbers and requirements added by the team ---


async def test_team_adds_edits_and_removes_a_number(api, business_db):
    b = await bridge(api, business_db, board=True)
    created = await add_number(b, "+92 300 777 0001")
    assert created.status_code == 201, created.text
    number = created.json()
    assert number["phone"] == WRITER and number["active"] is True and number["source"] == "manual"

    dup = await add_number(b, WRITER)
    assert dup.status_code >= 400 and dup.json()["error"]["code"] == "NUMBER_EXISTS"
    bad = await add_number(b, "12")
    assert bad.status_code >= 400 and bad.json()["error"]["code"] == "PHONE_INVALID"

    listed = (await b.pi.api.get(NUMBERS)).json()
    assert [n["workspace"] for n in listed["numbers"]] == ["Mendeez"]
    assert listed["workspaces"] == ["Mendeez"]

    changed = await b.pi.api.patch(f"{NUMBERS}/{number['id']}", json={"active": False})
    assert changed.status_code == 200 and changed.json()["active"] is False

    gone = await b.pi.api.delete(f"{NUMBERS}/{number['id']}")
    assert gone.status_code == 204
    assert (await b.pi.api.get(NUMBERS)).json()["numbers"] == []
    await b.pi.close()


async def test_team_adds_a_requirement_by_hand(api, business_db):
    b = await bridge(api, business_db, board=True)
    response = await b.pi.api.post(
        "/api/v1/pi/nori-board/items",
        json={
            "title": "Barcode labels for returns",
            "kind": "module",
            "workspace": "Hazari",
            "priority": "high",
        },
    )
    assert response.status_code == 201, response.text
    card = response.json()
    assert card["kind"] == "nori" and card["priority"] == "high"
    assert card["nori"]["source"] == "manual" and card["nori"]["workspace"] == "Hazari"
    assert [c["title"] for c in await cards(b)] == ["Barcode labels for returns"]
    await b.pi.close()


async def test_nori_cards_are_never_closed_by_the_board_sync(api, business_db):
    b = await bridge(api, business_db, board=True)
    await push(b, push_payload())
    for _ in range(3):  # every read of the board runs the sync
        found = await cards(b)
        assert [c["column"] for c in found] == ["todo"]
    await b.pi.close()


async def test_other_card_kinds_have_no_nori_facts(api, business_db):
    b = await bridge(api, business_db, board=True)
    task = await b.pi.api.post("/api/v1/pi/team-board/tasks", json={"title": "Order cards"})
    assert task.status_code == 201
    assert task.json()["nori"] is None
    await b.pi.close()


# --- a message from a number on the registry ---


async def test_registry_number_is_filed_and_answered_without_the_brain_or_nori(api, business_db):
    b = await bridge(api, business_db, board=True)
    assert (await add_number(b)).status_code == 201

    await b.say(WRITER, "The stock export is not working, please look", "wamid.board-1")

    assert b.nori.requests == []  # pi asked nobody: the registry is pi's own
    # The chat is kept for the team: the message is in the inbox, the chat is in human mode (the
    # brain stays silent) and the only outbound line is the one-time board acknowledgement.
    [inbound] = await b.inbound_rows("wamid.board-1")
    conversation = await b.pi.db.get(PiConversation, inbound.conversation_id)
    assert conversation.mode == "human"
    assert await outbound_bodies(b) == [BOARD_ACK]
    found = await cards(b)
    assert len(found) == 1
    assert found[0]["title"] == "The stock export is not working, please look"
    assert found[0]["nori"]["item_kind"] == "problem"
    assert found[0]["nori"]["workspace"] == "Mendeez"
    assert found[0]["nori"]["person"] == "Sara"
    assert found[0]["nori"]["department"] == "Stock"
    assert found[0]["nori"]["source"] == "whatsapp"
    assert found[0]["nori"]["conversation_id"] == str(inbound.conversation_id)
    assert WRITER not in repr(found)  # the card carries a masked number only
    await b.pi.close()


async def test_a_repeated_whatsapp_message_is_one_card_and_one_answer(api, business_db):
    b = await bridge(api, business_db, board=True)
    await add_number(b)
    await b.say(WRITER, "We need a van sales module", "wamid.board-2")
    await b.say(WRITER, "We need a van sales module", "wamid.board-2")
    assert await outbound_bodies(b) == [BOARD_ACK]
    assert len(await cards(b)) == 1
    await b.pi.close()


async def test_card_text_is_stored_without_card_numbers(api, business_db):
    b = await bridge(api, business_db, board=True)
    await add_number(b)
    await b.say(WRITER, "Charge fails for card 4111 1111 1111 1111 on the till", "wamid.board-3")
    task = await b.pi.db.scalar(select(PiTask).where(PiTask.idempotency_key.like("board:nori:%")))
    assert task is not None
    assert "4111" not in task.description and "4111" not in task.title
    await b.pi.close()


async def test_an_emergency_or_a_stop_is_not_filed_and_not_answered_by_the_board(api, business_db):
    b = await bridge(api, business_db, board=True)
    await add_number(b)
    await b.say(WRITER, "My father collapsed, I need an ambulance now", "wamid.board-e1")
    await b.say(WRITER, "Please stop messaging me", "wamid.board-e2")
    assert BOARD_ACK not in b.texts_to(WRITER)
    assert await cards(b) == []
    await b.pi.close()


async def test_a_switched_off_number_and_a_stranger_carry_on_as_before(api, business_db):
    b = await bridge(api, business_db, board=True)
    created = (await add_number(b)).json()
    await b.pi.api.patch(f"{NUMBERS}/{created['id']}", json={"active": False})

    await b.say(WRITER, "hello there", "wamid.board-4")
    await b.say(STRANGER, "hello there", "wamid.board-5")

    assert await cards(b) == []
    assert BOARD_ACK not in b.texts_to(WRITER) + b.texts_to(STRANGER)
    assert len(await b.inbound_rows("wamid.board-4")) == 1  # pi's own pipeline took both
    assert len(await b.inbound_rows("wamid.board-5")) == 1
    await b.pi.close()


async def test_board_flag_off_means_a_registry_number_is_not_filed(api, business_db):
    b = await bridge(api, business_db)  # enabled, board off
    await add_number(b)
    await b.say(WRITER, "We need a van sales module", "wamid.board-6")
    assert await cards(b) == []
    assert BOARD_ACK not in b.texts_to(WRITER)
    await b.pi.close()


async def test_a_failure_while_filing_asks_the_person_to_resend_and_keeps_no_claim(
    api, business_db, monkeypatch
):
    from app.modules.pi_saas.nori_board import service

    b = await bridge(api, business_db, board=True)
    await add_number(b)

    async def broken(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(service, "file_item", broken)
    await b.say(WRITER, "We need a van sales module", "wamid.board-7")
    assert len(b.texts_to(WRITER)) == 1 and "send it again" in b.texts_to(WRITER)[0]

    monkeypatch.undo()
    # The failed filing saved no claim, so nothing is left half done. A real resend is a new
    # WhatsApp message with its own id (pi never processes one id twice).
    left = await b.pi.db.scalar(
        select(func.count())
        .select_from(PiNoriBridgeLog)
        .where(PiNoriBridgeLog.kind == "inbound", PiNoriBridgeLog.outcome == "claimed")
    )
    assert left == 0
    assert await cards(b) == []
    assert (
        await b.pi.db.scalar(
            select(PiMessage.id).where(PiMessage.provider_message_id == "wamid.board-7")
        )
        is None
    )
    await b.say(WRITER, "We need a van sales module", "wamid.board-7b")
    assert await outbound_bodies(b) == [BOARD_ACK]
    assert len(await cards(b)) == 1
    assert await b.pi.db.scalar(select(PiNoriItem.id).limit(1)) is not None
    await b.pi.close()


# --- the numbers door: nori tells pi about a team member ---


def number_payload(ref="m-1", **extra):
    return {
        "ref": ref,
        "workspace": "Mendeez",
        "person": "Sara",
        "role": "Head of Stock",
        "department": "Stock",
        "phone": "+92 300 777 0002",
        "active": True,
        "ts": int(time.time() * 1000),
        **extra,
    }


async def push_number(b, payload, *, secret=SECRET):
    body, sig = signed(secret, payload)
    return await b.pi.api.post(
        "/api/pi/nori-numbers",
        content=body,
        headers={"x-workzap-signature": sig, "content-type": "application/json"},
    )


async def registry(b):
    response = await b.pi.api.get(NUMBERS)
    assert response.status_code == 200, response.text
    return response.json()["numbers"]


async def test_numbers_door_is_off_until_the_board_flag_is_on(api, business_db):
    b = await bridge(api, business_db)
    response = await push_number(b, number_payload())
    assert response.status_code == 503
    assert response.json()["reason"] == "disabled"
    await b.pi.close()


async def test_numbers_door_adds_then_updates_and_a_bad_signature_changes_nothing(api, business_db):
    b = await bridge(api, business_db, board=True)
    bad = await push_number(b, number_payload(), secret="x" * 40)
    assert bad.status_code == 401
    assert await registry(b) == []

    first = await push_number(b, number_payload())
    assert first.status_code == 200, first.text
    assert first.json() == {"ok": True, "created": True}
    again = await push_number(
        b, number_payload(department="Warehouse", ts=int(time.time() * 1000) + 5)
    )
    assert again.json() == {"ok": True, "created": False}
    rows = await registry(b)
    assert len(rows) == 1
    assert rows[0]["person"] == "Sara (Head of Stock)"
    assert rows[0]["department"] == "Warehouse"
    assert rows[0]["source"] == "nori"
    assert rows[0]["active"] is True
    await b.pi.close()


async def test_numbers_door_refusals(api, business_db):
    b = await bridge(api, business_db, board=True)
    stamp = int(time.time() * 1000)
    cases = [
        (number_payload(phone="12"), "bad_phone"),
        (number_payload(ref="bad ref"), "bad_ref"),
        (number_payload(workspace=""), "bad_workspace"),
        (number_payload(department="d" * 81), "bad_item"),
        (number_payload(active="yes"), "bad_item"),
        (number_payload(ts=stamp - 3_600_000), "stale"),
    ]
    for payload, reason in cases:
        response = await push_number(b, payload)
        assert response.json()["reason"] == reason, (reason, response.text)
    assert await registry(b) == []
    fixed = number_payload()
    assert (await push_number(b, fixed)).status_code == 200
    assert (await push_number(b, fixed)).status_code == 409
    await b.pi.close()


async def test_nori_can_switch_a_number_off_and_a_hand_added_number_stays_the_teams(
    api, business_db
):
    b = await bridge(api, business_db, board=True)
    assert (await add_number(b, phone="923007770003")).status_code in (200, 201)
    await push_number(b, number_payload(phone="923007770003", active=False))
    row = next(r for r in await registry(b))
    assert row["active"] is False and row["source"] == "manual"
    # nori cannot switch a hand-added number back on: the team's switch wins
    await push_number(
        b, number_payload(phone="923007770003", active=True, ts=int(time.time() * 1000) + 7)
    )
    assert next(r for r in await registry(b))["active"] is False
    await b.pi.close()


# --- sending a registry person's card back to nori (default off) ---

LINKED = "923007770009"


async def link_number(b, phone=LINKED, ref="nori-link:w1:923007770009"):
    response = await push_number(b, number_payload(ref=ref, phone=phone))
    assert response.status_code == 200, response.text


async def item_rows(b):
    return list(
        await b.pi.db.scalars(
            select(PiNoriItem)
            .where(PiNoriItem.source == "whatsapp")
            .order_by(PiNoriItem.created_at)
        )
    )


async def sweep(b):
    return await forward_due(b.pi.db, b.pi.app.state.settings, b.pi.ctx["http"])


async def test_a_registry_persons_card_goes_to_nori_once_with_its_ref_and_no_phone(
    api, business_db
):
    b = await bridge(api, business_db, board=True, forward=True)
    await link_number(b)
    await b.say(LINKED, "We need a meeting module, my card is 4111 1111 1111 1111", "wamid.fw-1")
    assert b.nori.board_cards == []  # nothing leaves pi until the sweep runs
    assert await sweep(b) == 1
    assert len(b.nori.board_cards) == 1
    sent = b.nori.board_cards[0]
    assert sent["ref"] == "nori-link:w1:923007770009"
    assert sent["card_id"] and sent["kind"] in {"feature", "problem", "question", "meeting"}
    assert "phone" not in sent
    assert "923007770009" not in sent["text"] + sent.get("person", "")  # only in nori's own ref
    assert "4111" not in sent["text"]  # the redacted board text, never the raw message
    row = (await item_rows(b))[0]
    assert row.forwarded_at is not None and row.forward_note == "sent"
    assert await sweep(b) == 0 and len(b.nori.board_cards) == 1
    await b.pi.close()


async def test_forwarding_is_off_unless_the_workspace_turns_it_on(api, business_db):
    b = await bridge(api, business_db, board=True)  # forward not set
    await link_number(b)
    await b.say(LINKED, "We need van sales", "wamid.fw-2")
    assert await sweep(b) == 0
    assert b.nori.board_cards == []
    assert (await item_rows(b))[0].forwarded_at is None
    # turning it on later sends the owed card
    await b.settings(enabled=True, board=True, forward=True)
    assert await sweep(b) == 1
    await b.pi.close()


async def test_a_number_added_by_hand_is_never_sent_to_nori(api, business_db):
    b = await bridge(api, business_db, board=True, forward=True)
    await add_number(b, phone=LINKED)
    await b.say(LINKED, "We need van sales", "wamid.fw-3")
    row = (await item_rows(b))[0]
    assert row.forward_ref is None
    assert await sweep(b) == 0 and b.nori.board_cards == []
    await b.pi.close()


async def test_a_refusal_is_final_and_a_failure_is_retried(api, business_db):
    b = await bridge(api, business_db, board=True, forward=True)
    await link_number(b)
    await b.say(LINKED, "We need van sales", "wamid.fw-4")
    b.nori.mode = "500"
    assert await sweep(b) == 0
    row = (await item_rows(b))[0]
    assert row.forwarded_at is None and row.forward_attempts == 1
    b.nori.mode = "ok"
    b.nori.board_card_reason = "unknown_ref"
    from app.modules.pi_saas.nori_credits.resilience import reset_breakers

    reset_breakers()
    assert await sweep(b) == 0
    await b.pi.db.refresh(row)
    assert row.forward_note == "unknown_ref" and row.forward_attempts >= 6
    calls = len(b.nori.calls("/api/pi/board-card"))
    assert await sweep(b) == 0 and len(b.nori.calls("/api/pi/board-card")) == calls
    await b.pi.close()


# --- a photo or file goes to nori as a signed link (off unless forward_media) ---


async def media_card(b, mid="wamid.fm-1"):
    b.pi.app.state.settings.integrations_public_base_url = "https://pi.test"
    await link_number(b)
    await b.pi.process("the screen as it looks", mid, sender=LINKED, kind="image")


async def test_a_photo_card_has_no_link_while_media_forwarding_is_off(api, business_db):
    b = await bridge(api, business_db, board=True, forward=True)  # forward_media not set
    await media_card(b)
    assert await sweep(b) == 1
    assert "files" not in b.nori.board_cards[0]
    await b.pi.close()


async def test_a_photo_card_carries_a_signed_link_when_media_forwarding_is_on(api, business_db):
    b = await bridge(api, business_db, board=True, forward=True, forward_media=True)
    await media_card(b, "wamid.fm-2")
    assert await sweep(b) == 1
    [file] = b.nori.board_cards[0]["files"]
    assert file["kind"] == "image"
    assert file["url"].startswith("https://pi.test/api/pi/nori-media/")
    await b.pi.close()


async def test_the_media_link_is_refused_unless_genuine_and_switched_on(
    api, business_db, monkeypatch
):
    from app.modules.pi.whatsapp import WhatsApp
    from app.modules.pi_saas.nori_board import media_link

    async def fake_media(self, media_id, token, *, url="", mime=""):
        return b"PNGDATA", "image/png"

    monkeypatch.setattr(WhatsApp, "media", fake_media)
    b = await bridge(api, business_db, board=True, forward=True, forward_media=True)
    await media_card(b, "wamid.fm-3")
    item = (await item_rows(b))[0]
    link = media_link.url_for(b.pi.app.state.settings, SECRET, item.id)
    path = link.removeprefix("https://pi.test")
    ok = await b.pi.api.get(path)
    assert ok.status_code == 200 and ok.content == b"PNGDATA"
    assert "no-store" in ok.headers["cache-control"]
    bad = await b.pi.api.get(path[:-3] + "000")
    assert bad.status_code == 404
    await b.settings(enabled=True, board=True, forward=True)  # media switched off
    assert (await b.pi.api.get(path)).status_code == 404
    await b.pi.close()


# --- the inbox list labels a registry person's chat ---


async def test_the_inbox_labels_a_registry_chat_with_its_nori_workspace(api, business_db):
    b = await bridge(api, business_db, board=True)
    await add_number(b)
    await b.say(WRITER, "The stock export is not working", "wamid.lbl-1")
    stranger = "923005559999"
    await b.pi.process("hello there", "wamid.lbl-2", sender=stranger)
    response = await b.pi.api.get("/api/v1/pi/conversations")
    assert response.status_code == 200, response.text
    labels = {
        c["customer_phone"] or c["customer_name"]: c["nori_workspace"]
        for c in response.json()["items"]
    }
    assert "Mendeez" in labels.values()
    assert list(labels.values()).count(None) == len(labels) - 1
    await b.pi.close()
