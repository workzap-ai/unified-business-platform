"""Spec v1.6, 19.8: the board link names only a message; the board as sent stays on the server
and goes with the customer's data when it is erased (R-PRIV-06)."""

import base64
import json

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, say, workspace
from test_pi_brain_visual_cards import model

from app.modules.pi.models import PiMessage

pytestmark = pytest.mark.integration


async def board_rows(db):
    rows = await db.scalars(select(PiMessage))
    return [m for m in rows if (m.media or {}).get("visual") == "board"]


async def test_the_board_link_carries_no_problem_words_and_stops_resolving_after_erase(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await say(pi, "Best-sellers run out and cashiers are late on weekends", "be-1")
    await say(pi, "That's all", "be-2")
    images = [m for m in pi.sent if m.get("type") == "image"]
    assert len(images) == 1
    link = images[0]["image"]["link"]
    path = link[link.index("/brain-visuals/") :]

    token = path.split("/")[2]
    claims = json.loads(base64.urlsafe_b64decode(token.split(".")[0] + "=="))
    assert claims.get("m") and "g" not in claims
    assert "Best-sellers" not in json.dumps(claims) and "Cashiers" not in json.dumps(claims)

    [picture] = await board_rows(business_db)
    assert picture.media["board_snapshot"]  # the board as sent, on the server
    assert (await api.get(f"/api/v1/pi-app{path}")).status_code == 200

    conversation = await pi.conversation()
    erased = await api.post(
        f"/api/v1/pi/brain-erasure/{conversation.customer_id}", json={"confirm": True}
    )
    assert erased.status_code == 200, erased.text
    business_db.expire_all()

    assert all(
        not (m.media or {}).get("board_snapshot")
        for m in await business_db.scalars(select(PiMessage))
    )
    assert (
        await api.get(f"/api/v1/pi-app{path}")
    ).status_code == 404  # the link no longer resolves
    await pi.close()


def again(context, n):
    from test_pi_brain_problems import create
    from test_pi_service_conversations import turn

    return turn(
        reply="Noted. Anything else getting in the way?",
        language="en",
        problem_ops=[create("Stock runs out again", "Stock runs out again.")],
    )


async def test_an_old_board_link_stays_404_after_an_erase_even_when_new_problems_are_recorded(
    api, business_db, monkeypatch
):
    from test_pi_brain_problems import problems_of

    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await say(pi, "Best-sellers run out and cashiers are late on weekends", "bf-1")
    await say(pi, "That's all", "bf-2")
    link = [m for m in pi.sent if m.get("type") == "image"][0]["image"]["link"]
    path = link[link.index("/brain-visuals/") :]
    assert (await api.get(f"/api/v1/pi-app{path}")).status_code == 200

    conversation = await pi.conversation()
    erased = await api.post(
        f"/api/v1/pi/brain-erasure/{conversation.customer_id}", json={"confirm": True}
    )
    assert erased.status_code == 200, erased.text
    business_db.expire_all()

    adaptive(monkeypatch, again)  # the same chat records new problems after the erase
    await say(pi, "Stock runs out again at the main shop", "bf-3")
    _, rows = await problems_of(business_db, pi)
    assert rows, "the chat must hold new problems for this test to mean anything"
    assert (await api.get(f"/api/v1/pi-app{path}")).status_code == 404  # no live fallback
    await pi.close()
