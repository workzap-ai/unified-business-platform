"""The Nori Platform board on the disposable database: nori's signed push (the door), numbers added
by hand, a message from such a number filed by the bridge hook, and the board itself. A fake nori
and a fake WhatsApp provider on httpx mock transports: no network. Run only through
scripts/pi-test-env.sh."""

import time

import pytest
from sqlalchemy import func, select
from test_nori_credits_bridge import bridge

from app.modules.pi.models import PiMessage
from app.modules.pi_saas.models import PiTask
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

    assert b.texts_to(WRITER) == [BOARD_ACK]
    assert b.nori.requests == []  # pi asked nobody: the registry is pi's own
    assert await b.inbound_rows("wamid.board-1") == []  # the brain's pipeline never took it
    found = await cards(b)
    assert len(found) == 1
    assert found[0]["title"] == "The stock export is not working, please look"
    assert found[0]["nori"]["item_kind"] == "problem"
    assert found[0]["nori"]["workspace"] == "Mendeez"
    assert found[0]["nori"]["person"] == "Sara"
    assert found[0]["nori"]["department"] == "Stock"
    assert found[0]["nori"]["source"] == "whatsapp"
    assert WRITER not in repr(found)  # the card carries a masked number only
    await b.pi.close()


async def test_a_repeated_whatsapp_message_is_one_card_and_one_answer(api, business_db):
    b = await bridge(api, business_db, board=True)
    await add_number(b)
    await b.say(WRITER, "We need a van sales module", "wamid.board-2")
    await b.say(WRITER, "We need a van sales module", "wamid.board-2")
    assert b.texts_to(WRITER) == [BOARD_ACK]
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
    await b.say(WRITER, "We need a van sales module", "wamid.board-7b")
    assert b.texts_to(WRITER)[-1] == BOARD_ACK
    assert len(await cards(b)) == 1
    assert await b.pi.db.scalar(select(PiNoriItem.id).limit(1)) is not None
    assert (
        await b.pi.db.scalar(
            select(PiMessage.id).where(PiMessage.provider_message_id.like("wamid.board-7%"))
        )
        is None
    )
    await b.pi.close()
