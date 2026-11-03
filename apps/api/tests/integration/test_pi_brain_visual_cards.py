"""The problem board, the tap-to-correct list and the progress card (spec 8.11.2)."""

import pytest
from test_pi_brain_problems import OPENING, adaptive, create, say, workspace
from test_pi_service_conversations import turn

pytestmark = pytest.mark.integration


def model(context, n):
    if n == 1:
        ops = [
            create("Best-sellers run out in two shops", "Best-sellers run out."),
            create("Cashiers late on weekends", "Cashiers come late.", "people_staff"),
        ]
        return turn(
            reply=f"{OPENING} Noted both. Anything else getting in the way?",
            language="en",
            problem_ops=ops,
        )
    return turn(reply="Thanks, noted.", language="en")


async def test_the_sorted_summary_comes_with_a_board_picture_and_a_list_to_correct(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await say(pi, "Best-sellers run out and cashiers are late on weekends", "bv-1")
    await say(pi, "That's all", "bv-2")
    images = [m for m in pi.sent if m.get("type") == "image"]
    from sqlalchemy import select

    from app.modules.pi.models import PiMessage

    pictures = [
        m
        for m in await business_db.scalars(select(PiMessage))
        if (m.media or {}).get("visual") == "board"
    ]
    # pi's own reply with the summary's inbound marker, so a takeover or a newer message holds
    # it back exactly as it holds the summary.
    assert len(pictures) == 1 and pictures[0].sender_type == "ai"
    assert pictures[0].media.get("service_inbound_at")
    assert len(images) == 1 and "/brain-visuals/" in images[0]["image"]["link"]
    assert images[0]["image"]["link"].endswith("/board.png")
    lists = [
        m for m in pi.sent if m.get("type") == "interactive" and m["interactive"]["type"] == "list"
    ]
    assert len(lists) == 1
    body = lists[0]["interactive"]["body"]["text"]
    assert body.startswith("Here is what you have told me so far")  # the text is always sent
    rows = lists[0]["interactive"]["action"]["sections"][0]["rows"]
    assert [r["title"] for r in rows] == ["Best-sellers run out in", "Cashiers late on weekend"]
    assert all(len(r["title"]) <= 24 for r in rows) and len(rows) <= 10
    # The link serves the picture; a forged link and a wrong name do not.
    link = images[0]["image"]["link"]
    path = link[link.index("/brain-visuals/") :]
    served = await api.get(f"/api/v1/pi-app{path}")
    assert served.status_code == 200 and served.headers["content-type"] == "image/png"
    assert served.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert (
        await api.get(f"/api/v1/pi-app{path.replace('board.png', 'progress.png')}")
    ).status_code == 404
    assert (await api.get("/api/v1/pi-app/brain-visuals/forged.token/board.png")).status_code == 404
    await pi.close()


async def test_a_chat_with_no_summary_gets_no_picture(api, business_db, monkeypatch):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await say(pi, "Best-sellers run out and cashiers are late on weekends", "bv-3")
    assert [m for m in pi.sent if m.get("type") == "image"] == []
    await pi.close()
