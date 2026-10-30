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
