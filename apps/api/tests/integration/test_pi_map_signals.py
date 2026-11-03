# ruff: noqa: F811
"""B3 and B4 from the portal map (platform spec Book 5, 5.4): an edit marks the map reviewed, a
rank marks it ranked, only with the Solution Box offer on, and only on the owner's own chat."""

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, say, workspace
from test_pi_customer_portal import (  # noqa: F401  (app and provider are fixtures)
    PORTAL,
    _business_with_chat,
    _sign_in,
    app,
    provider,
)
from test_pi_map_dashboard import conversations_of, csrf, note, second_customer
from test_pi_map_share import FIRST, model

from app.modules.pi import box
from app.modules.pi.problem_models import PiProblem

pytestmark = pytest.mark.integration


async def test_a_portal_edit_marks_the_map_reviewed_and_ranked_only_with_the_box_on(
    app, provider, business_db, monkeypatch
):
    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    customer = await _sign_in(app, provider)
    cid = (await customer.get(f"{PORTAL}/conversations")).json()[0]["id"]
    [conversation] = await conversations_of(business_db)
    await note(business_db, conversation, 1, "purana maal ruka hai")
    await note(business_db, conversation, 2, "paisa phansa")
    path = f"{PORTAL}/conversations/{cid}/map"
    await customer.get(path)

    # box off: the rank is stored and drawn, the brief is never touched
    monkeypatch.setattr(box, "box_offer_enabled", lambda rules: False)
    off = await customer.post(
        f"{path}/problems/P1", json={"action": "rank", "priority": 1}, headers=csrf(customer)
    )
    assert off.status_code == 200
    nodes = off.json()["latest"]["map"]["nodes"]
    assert nodes[0]["rank"] == 1 and "rank" not in nodes[1]
    await business_db.refresh(conversation)
    assert not (conversation.service_brief or {}).get("map_reviewed")
    assert not (conversation.service_brief or {}).get("ranked")

    # box on: any change is B3, a rank is B4 as well
    monkeypatch.setattr(box, "box_offer_enabled", lambda rules: True)
    park = await customer.post(
        f"{path}/problems/P2", json={"action": "park"}, headers=csrf(customer)
    )
    assert park.status_code == 200
    await business_db.refresh(conversation)
    assert conversation.service_brief["map_reviewed"] is True
    assert not conversation.service_brief.get("ranked")
    rank = await customer.post(
        f"{path}/problems/P2", json={"action": "rank", "priority": 2}, headers=csrf(customer)
    )
    assert rank.status_code == 200
    await business_db.refresh(conversation)
    assert conversation.service_brief["ranked"] is True
    # a rank needs a priority within bounds; clearing it is its own action
    for wrong in ({}, {"priority": 0}, {"priority": 99}):
        refused = await customer.post(
            f"{path}/problems/P1", json={"action": "rank", **wrong}, headers=csrf(customer)
        )
        assert refused.status_code == 422
    clear = await customer.post(
        f"{path}/problems/P1", json={"action": "unrank"}, headers=csrf(customer)
    )
    assert "rank" not in clear.json()["latest"]["map"]["nodes"][0]
    await business.aclose()
    await customer.aclose()


async def test_one_owners_map_edit_never_marks_another_conversation(
    app, provider, business_db, monkeypatch
):
    monkeypatch.setattr(box, "box_offer_enabled", lambda rules: True)
    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    mine, theirs = await second_customer(app, provider, business, business_db)
    await note(business_db, mine, 1, "mera masla")
    other = await note(business_db, theirs, 1, "unka masla")
    a = await _sign_in(app, provider)
    path = f"{PORTAL}/conversations"
    refused = await a.post(
        f"{path}/{theirs.id}/map/problems/P1",
        json={"action": "rank", "priority": 1},
        headers=csrf(a),
    )
    assert refused.status_code == 404
    await a.get(f"{path}/{mine.id}/map")
    done = await a.post(
        f"{path}/{mine.id}/map/problems/P1",
        json={"action": "rank", "priority": 1},
        headers=csrf(a),
    )
    assert done.status_code == 200
    await business_db.refresh(mine)
    await business_db.refresh(theirs)
    await business_db.refresh(other)
    assert mine.service_brief["map_reviewed"] and mine.service_brief["ranked"]
    assert not (theirs.service_brief or {}).get("map_reviewed")
    assert not (theirs.service_brief or {}).get("ranked")
    assert "rank:1" not in (other.tags or [])
    await business.aclose()
    await a.aclose()


async def _settings(api, **brain):
    rules = {"pi_mode": "brain", "brain": {"map_share": True, **brain}}
    response = await api.patch("/api/v1/pi/settings/response_rules", json={"value": rules})
    assert response.status_code == 200, response.text


async def test_whatsapp_replies_set_b3_b4_and_b5_with_the_box_on(api, business_db, monkeypatch):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await _settings(api, box_offer=True)
    await say(pi, FIRST, "sg-1")  # raised on their own, and the map goes out after pi's reply
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert not (conversation.service_brief or {}).get("map_reviewed")
    voluntary = await business_db.scalars(select(PiProblem.raised_voluntarily))
    assert all(voluntary.all())
    await say(pi, "sahi hai", "sg-2")  # the reply right after the map picture
    await business_db.refresh(conversation)
    assert conversation.service_brief["map_reviewed"] is True
    assert not conversation.service_brief.get("ranked")
    await say(pi, "pehle ye wala masla", "sg-3")
    await business_db.refresh(conversation)
    assert conversation.service_brief["ranked"] is True
    await pi.close()


async def test_a_yes_that_does_not_follow_a_map_does_not_review_it(api, business_db, monkeypatch):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await _settings(api, box_offer=True, map_share=False)
    await say(pi, FIRST, "sg-4")
    await say(pi, "sahi hai", "sg-5")
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert not (conversation.service_brief or {}).get("map_reviewed")
    await pi.close()


async def test_with_the_box_off_the_brief_gets_no_signals(api, business_db, monkeypatch):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await _settings(api)
    await say(pi, FIRST, "sg-6")
    await say(pi, "sahi hai", "sg-7")
    await say(pi, "pehle ye wala masla", "sg-8")
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    brief = conversation.service_brief or {}
    assert not brief.get("map_reviewed") and not brief.get("ranked")
    assert not any((await business_db.scalars(select(PiProblem.raised_voluntarily))).all())
    await pi.close()
