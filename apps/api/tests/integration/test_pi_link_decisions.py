"""Staff decisions on suggested problem links (spec 8.10): decide route and the confidence floor."""

import pytest
from sqlalchemy import select
from test_pi_brain_problems import OPENING, adaptive, create, say, workspace
from test_pi_service_conversations import turn

from app.modules.pi.problem_models import PiProblemLink
from app.modules.pi.problems import ProblemOp

pytestmark = pytest.mark.integration
L = "/api/v1/pi/brain-learning"


def model(context, n):
    refs = {p["title"]: p["ref"] for p in context["noted_problems"]}
    if n == 1:
        ops = [
            create("Stock runs out in Shop B", "Shop B runs out."),
            create("Cashiers late on weekends", "Cashiers come late.", "people_staff"),
            create("Deliveries arrive late", "Deliveries are late.", "orders_fulfilment"),
        ]
        return turn(
            reply=f"{OPENING} Noted all three. Anything else?", language="en", problem_ops=ops
        )
    a, b, c = (
        refs["Stock runs out in Shop B"],
        refs["Cashiers late on weekends"],
        refs["Deliveries arrive late"],
    )
    ops = [
        ProblemOp(op="link", ref=b, to=a, link_type="same_area", confidence=0.9),
        ProblemOp(op="link", ref=c, to=a, link_type="same_area", confidence=0.55),  # too unsure
    ]
    return turn(reply="Noted the connection. Anything else?", language="en", problem_ops=ops)


async def test_a_link_below_the_floor_is_not_suggested_and_staff_can_decide_the_rest(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await say(pi, "Shop B runs out, cashiers are late, deliveries late", "ld-1")
    await say(pi, "The first two seem connected", "ld-2")
    business_db.expire_all()
    [link] = (await business_db.scalars(select(PiProblemLink))).all()  # the 0.55 one was skipped
    assert float(link.confidence) == 0.9 and link.status == "suggested"
    listed = (await api.get(f"{L}/links")).json()["items"]
    assert [i["id"] for i in listed] == [str(link.id)]
    assert (
        await api.post(f"{L}/links/{link.id}/decide", json={"decision": "maybe"})
    ).status_code == 422
    done = await api.post(f"{L}/links/{link.id}/decide", json={"decision": "confirm"})
    assert done.status_code == 200 and done.json()["status"] == "confirmed"
    again = await api.post(f"{L}/links/{link.id}/decide", json={"decision": "reject"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "LINK_DECIDED"
    assert (await api.get(f"{L}/links")).json()["items"] == []
    await pi.close()
