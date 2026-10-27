"""Sharing the problem map in the chat (spec Book 5, 4.4), behind response_rules.brain.map_share."""

import pytest
from sqlalchemy import select
from test_pi_brain_problems import OPENING, adaptive, create, say, workspace
from test_pi_service_conversations import turn

from app.modules.pi import map_render
from app.modules.pi.box_models import PiMapVersion
from app.modules.pi.models import PiMessage

pytestmark = pytest.mark.integration


def model(context, n):
    if n == 1:
        ops = [
            create("Old stock is stuck", "purana maal ruka hai"),
            create("Cash is tied up", "paisa phansa hai", "cash_collections"),
            create("Suppliers paid late", "suppliers ko late payment", "suppliers_purchasing"),
        ]
        return turn(
            reply=f"{OPENING} Noted all three. Anything else getting in the way?",
            language="en",
            problem_ops=ops,
        )
    return turn(reply="Thanks, noted.", language="en")


async def enable(api, on=True):
    rules = {"pi_mode": "brain", "brain": {"map_share": True}} if on else {"pi_mode": "brain"}
    response = await api.patch("/api/v1/pi/settings/response_rules", json={"value": rules})
    assert response.status_code == 200, response.text


async def maps(db):
    return [
        m
        for m in await db.scalars(select(PiMessage).order_by(PiMessage.created_at))
        if str((m.media or {}).get("visual", "")).startswith("map")
    ]


FIRST = "Old stock is stuck, cash is tied up and my suppliers are paid late, it is a mess"


async def test_with_the_flag_off_nothing_is_shared_or_saved(api, business_db, monkeypatch):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await say(pi, FIRST, "ms-1")
    assert await maps(business_db) == []
    assert (await business_db.scalars(select(PiMapVersion))).all() == []
    await pi.close()


async def test_the_first_map_is_sent_as_a_picture_with_caption_alt_and_one_question(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await enable(api)
    await say(pi, FIRST, "ms-2")
    [shared] = await maps(business_db)
    assert shared.sender_type == "ai" and shared.media["visual"] == "map"
    assert shared.body.endswith("Are the links right?") and shared.body.count("?") == 1
    assert shared.media["alt"] and shared.media["map_version"] == 1
    assert shared.media.get("service_inbound_at")
    [version] = (await business_db.scalars(select(PiMapVersion))).all()
    assert version.shared_at is not None and str(version.shared_message_id) == str(shared.id)
    assert [n["label"] for n in version.map_json["nodes"]][0].startswith("purana maal")
    # the picture goes as the header of a quick-reply message: right, wrong, missing
    [card] = [m for m in pi.sent if m.get("type") == "interactive"]
    link = card["interactive"]["header"]["image"]["link"]
    titles = [b["reply"]["title"] for b in card["interactive"]["action"]["buttons"]]
    assert titles == ["The map is correct", "Something's wrong", "Something's missing"]
    assert link.endswith("/map.png") and "/brain-visuals/" in link
    served = await api.get(f"/api/v1/pi-app{link[link.index('/brain-visuals/') :]}")
    assert served.status_code == 200 and served.content[:8] == b"\x89PNG\r\n\x1a\n"
    # no new version, no new share on the next message (nothing changed, and the six-message limit)
    await say(pi, "That is all", "ms-3")
    assert len(await maps(business_db)) == 1
    await pi.close()


async def test_asking_for_the_map_sends_it_again_but_not_a_second_version(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await enable(api)
    await say(pi, FIRST, "ms-4")
    await say(pi, "show my problem map please", "ms-5")
    sent = await maps(business_db)
    assert len(sent) == 2 and {m.media["map_version"] for m in sent} == {1}
    assert len((await business_db.scalars(select(PiMapVersion))).all()) == 1
    await pi.close()


async def test_if_drawing_fails_the_same_map_goes_as_text(api, business_db, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("no font")

    adaptive(monkeypatch, model)
    monkeypatch.setattr(map_render, "render_map", broken)
    pi = await workspace(api, business_db)
    await enable(api)
    await say(pi, FIRST, "ms-6")
    [shared] = await maps(business_db)
    assert shared.media["visual"] == "map_text" and "image" not in shared.media
    assert "purana maal" in shared.body and shared.body.endswith("Are the links right?")
    assert [m for m in pi.sent if m.get("type") == "image"] == []
    await pi.close()
