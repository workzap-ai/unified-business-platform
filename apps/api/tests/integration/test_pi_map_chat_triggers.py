# ruff: noqa: F811
"""The map share triggers beyond the first (Book 5, 4.4, 4.9 and Part 6) in a real chat: the
check-in at the offer, the owner coming back, "pichli baar ka", more than nine problems, kept node
positions, never two pictures in one turn, the quiet-owner follow-up, the line that tells what the
owner changed on the dashboard, a real parked status. The model is mocked; the webhook, the worker,
the gates and the database are real."""

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, text, update
from test_pi_brain_followups import configure
from test_pi_brain_problems import OPENING, adaptive, create, say, workspace
from test_pi_customer_portal import (  # noqa: F401  (app and provider are fixtures)
    PORTAL,
    _business_with_chat,
    _sign_in,
    app,
    provider,
)
from test_pi_map_dashboard import conversations_of, csrf, note
from test_pi_map_share import FIRST, enable, maps, model
from test_pi_service_conversations import turn

from app.modules.pi import brain_followups, brain_visuals, map_builder, map_share
from app.modules.pi.box_models import PiMapVersion
from app.modules.pi.models import PiMessage
from app.modules.pi.problem_models import PiProblem, PiProblemRevision
from app.shared.scope import WorkspaceScope

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def any_hour(monkeypatch):
    monkeypatch.setattr(brain_followups, "quiet_until", lambda *a, **k: None)
    monkeypatch.setattr(brain_followups, "_friday_prayer", lambda tz: False)


def scope_of(conversation):
    return WorkspaceScope.system(
        conversation.tenant_id, conversation.environment_id, frozenset(), "test"
    )


async def days_ago(db, conversation, days):
    """Move everything said so far back in time (the test clock stands still)."""
    then = datetime.now(UTC) - timedelta(days=days)
    await db.execute(
        update(PiMessage)
        .where(PiMessage.conversation_id == conversation.id)
        .values(created_at=then)
    )
    conversation.last_inbound_at = then
    await db.flush()
    await db.refresh(conversation)


async def disable(api):
    """Switch map_share off again (a patch merges into the rules, so it is set to false)."""
    rules = {"pi_mode": "brain", "brain": {"map_share": False}}
    response = await api.patch("/api/v1/pi/settings/response_rules", json={"value": rules})
    assert response.status_code == 200, response.text


def served(pi, link):
    return f"/api/v1/pi-app{link[link.index('/brain-visuals/') :]}"


# --- a real parked status ----------


def migration():
    path = Path(__file__).parents[2] / "migrations/versions/0048_pi_map_parked_positions.py"
    spec = importlib.util.spec_from_file_location("migration_0048", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_the_migration_moves_parked_tags_to_the_status_and_keeps_the_other_tags(
    app, provider, business_db, monkeypatch
):
    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    [conversation] = await conversations_of(business_db)
    tagged = await note(business_db, conversation, 1, "a", tags=["parked", "rank:2"])
    plain = await note(business_db, conversation, 2, "b", tags=["rank:1"])
    done = await note(business_db, conversation, 3, "c", status="resolved", tags=["parked"])
    await business_db.execute(text(migration().CONVERT_PARKED_TAGS))
    for row in (tagged, plain, done):
        await business_db.refresh(row)
    assert (tagged.status, tagged.tags) == ("parked", ["rank:2"])
    assert (plain.status, plain.tags) == ("confirmed", ["rank:1"])
    assert (done.status, done.tags) == ("resolved", ["parked"])  # only problems in play
    await business.aclose()


async def test_parking_from_the_page_sets_the_status_reopening_clears_it_and_a_map_shows_it(
    app, provider, business_db, monkeypatch
):
    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    customer = await _sign_in(app, provider)
    cid = (await customer.get(f"{PORTAL}/conversations")).json()[0]["id"]
    [conversation] = await conversations_of(business_db)
    stock = await note(business_db, conversation, 1, "purana maal ruka hai")
    await note(business_db, conversation, 2, "paisa phansa")
    path = f"{PORTAL}/conversations/{cid}/map"
    await customer.get(path)
    parked = await customer.post(
        f"{path}/problems/P1", json={"action": "park"}, headers=csrf(customer)
    )
    assert parked.status_code == 200
    assert [n["status"] for n in parked.json()["latest"]["map"]["nodes"]] == ["parked", "open"]
    await business_db.refresh(stock)
    assert stock.status == "parked" and "parked" not in stock.tags
    again = await customer.post(
        f"{path}/problems/P1", json={"action": "park"}, headers=csrf(customer)
    )
    assert again.json()["latest"]["version"] == parked.json()["latest"]["version"]
    from app.modules.pi.problems import ProblemBook

    book = ProblemBook(business_db, scope_of(conversation), conversation.customer_id, "en")
    assert [p.number for p in await book.active()] == [2]  # out of the live set
    reopened = await customer.post(
        f"{path}/problems/P1", json={"action": "reopen"}, headers=csrf(customer)
    )
    assert reopened.json()["latest"]["map"]["nodes"][0]["status"] == "open"
    await business_db.refresh(stock)
    assert stock.status == "confirmed"
    assert [p.number for p in await book.active()] == [1, 2]
    reasons = list(
        await business_db.scalars(
            select(PiProblemRevision.reason).where(PiProblemRevision.by == "person")
        )
    )
    assert sorted(reasons) == ["parked", "reopened"]
    await business.aclose()
    await customer.aclose()


async def test_an_old_node_is_shown_from_last_time_until_the_owner_confirms_it(
    app, provider, business_db, monkeypatch
):
    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    customer = await _sign_in(app, provider)
    cid = (await customer.get(f"{PORTAL}/conversations")).json()[0]["id"]
    [conversation] = await conversations_of(business_db)
    old = await note(business_db, conversation, 1, "purana maal ruka hai")
    await note(business_db, conversation, 2, "paisa phansa")
    path = f"{PORTAL}/conversations/{cid}/map"
    first = (await customer.get(path)).json()["latest"]
    assert not any(n.get("stale") for n in first["map"]["nodes"])
    await business_db.execute(
        update(PiProblem)
        .where(PiProblem.id == old.id)
        .values(updated_at=datetime.now(UTC) - timedelta(days=100))
    )
    seen = (await customer.get(path)).json()["latest"]
    assert [bool(n.get("stale")) for n in seen["map"]["nodes"]] == [True, False]
    assert seen["version"] == first["version"] + 1  # the page shows it, so it is a new version
    # confirming a node that is not old changes nothing
    nothing = await customer.post(
        f"{path}/problems/P2", json={"action": "confirm"}, headers=csrf(customer)
    )
    assert nothing.json()["latest"]["version"] == seen["version"]
    confirmed = await customer.post(
        f"{path}/problems/P1", json={"action": "confirm"}, headers=csrf(customer)
    )
    assert confirmed.status_code == 200
    latest = confirmed.json()["latest"]
    assert not any(n.get("stale") for n in latest["map"]["nodes"])
    assert latest["version"] == seen["version"] + 1
    reasons = list(
        await business_db.scalars(
            select(PiProblemRevision.reason).where(PiProblemRevision.by == "person")
        )
    )
    assert reasons == ["confirmed"]
    await business.aclose()
    await customer.aclose()


# --- the owner comes back (Part 6) ----------


async def test_an_owner_back_after_a_day_gets_the_map_continuity_and_one_open_question(
    api, business_db, monkeypatch
):
    prompts = adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await enable(api)
    await say(pi, FIRST, "mt-1")
    assert len(await maps(business_db)) == 1
    conversation = await pi.conversation()
    await days_ago(business_db, conversation, 2)
    old = await business_db.scalar(select(PiProblem).where(PiProblem.number == 1))
    await business_db.execute(  # confirmed long ago and not touched since
        update(PiProblem)
        .where(PiProblem.customer_id == old.customer_id)
        .values(status="confirmed", updated_at=datetime.now(UTC) - timedelta(days=100))
    )
    await say(pi, "hello, I am back", "mt-2")
    shared = await maps(business_db)
    assert len(shared) == 2
    back = shared[-1]
    assert back.media["visual"] == "map" and back.media["map_version"] == 2  # the stale mark
    assert back.body.count("?") == 1 and back.body.rstrip().endswith(
        "Has anything changed since, or has a new problem come up?"
    )
    assert "Good to have you back. Here is the map from last time." in back.body
    assert "/customer" in back.body  # the dashboard link
    assert "marked from last time may have changed" in back.body  # nothing assumed still true
    assert "buttons" not in back.media  # an open question, not a yes or no
    assert "From last time" in " ".join(back.media["alt"])
    # the model was told it is a returning owner for this turn, and the chat moved on afterwards
    assert any("They are back after a day or more" in p for p in prompts[-3:])
    await business_db.refresh(conversation)
    assert conversation.flow_state != "S_RETURN"
    await pi.close()


async def test_a_return_with_the_flag_off_or_within_a_day_is_not_a_return(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await enable(api)
    await say(pi, FIRST, "mt-3")
    conversation = await pi.conversation()
    await days_ago(business_db, conversation, 0.5)
    await say(pi, "hello again", "mt-4")
    assert len(await maps(business_db)) == 1  # half a day: nothing new to share
    await disable(api)
    await days_ago(business_db, conversation, 3)
    await say(pi, "hello, back after days", "mt-5")
    assert len(await maps(business_db)) == 1
    await business_db.refresh(conversation)
    assert conversation.flow_state != "S_RETURN"
    await pi.close()


# --- the check-in at the offer, and never two pictures ----------


async def test_the_map_goes_before_the_offer_so_the_offers_question_stays_last(
    api, business_db, monkeypatch
):
    from test_pi_solution_ask_flow import scripted, solution_chat  # noqa: PLC0415
    from test_pi_solution_learning import an_industry  # noqa: PLC0415

    from app.modules.pi import box, solution_ask

    monkeypatch.setattr(box, "box_offer_enabled", lambda rules: True)
    monkeypatch.setattr(box, "can_offer", lambda facts: (True, "R2", "held open"))
    industry, problem = an_industry()
    pi, conversation, industry, problem = await solution_chat(
        api, business_db, monkeypatch, scripted(industry, problem)
    )
    response = await api.patch(
        "/api/v1/pi/settings/response_rules",
        json={
            "value": {
                "pi_mode": "brain",
                "brain": {"solution_mode": True, "learning_frozen": False, "map_share": True},
            }
        },
    )
    assert response.status_code == 200, response.text
    from app.modules.pi import brain_visual_queue

    order: list[list[str]] = []
    real = brain_visual_queue.attach_map

    async def spy(*args, **kwargs):
        result = await real(*args, **kwargs)
        order.append(result)  # the order pi sends them in (the test clock has no order)
        return result

    monkeypatch.setattr(brain_visual_queue, "attach_map", spy)
    await say(pi, "Can you tell me the solution", "mo-2")
    [sending] = order
    rows = [await business_db.get(PiMessage, i) for i in sending]
    assert [(r.media or {}).get("visual") for r in rows] == ["map", None]  # the map, then the offer
    shared = rows[0]
    assert shared.media["map_version"] == 1 and "?" not in shared.body
    assert "buttons" not in shared.media  # the offer's own question stays last
    assert rows[-1].body.rstrip().endswith(solution_ask.offer_line("en"))
    await business_db.refresh(conversation)
    assert conversation.service_brief.get("offer_asked") is True
    assert not conversation.service_brief.get("map_awaiting")  # the offer is the next question
    await pi.close()


async def test_asking_for_the_map_with_a_summary_due_sends_one_picture_not_two(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await enable(api)
    await say(pi, FIRST, "md-1")
    await say(pi, "show me the full list of my problems and the map", "md-2")
    pictures = [
        m
        for m in await pi.outbound()
        if (m.media or {}).get("visual") in ("board", "map") and m.status != "failed"
    ]
    per_turn = {}
    for m in pictures:
        per_turn.setdefault(m.media.get("service_inbound_at"), []).append(m.media["visual"])
    assert all(len(v) == 1 for v in per_turn.values()), per_turn
    await pi.close()


async def test_the_map_waits_when_the_board_picture_is_already_in_the_turn(
    api, business_db, monkeypatch
):
    from app.modules.pi import brain_visual_queue

    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await enable(api)
    await say(pi, FIRST, "md-3")
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    scope, settings = scope_of(conversation), api._transport.app.state.settings
    board = await brain_visual_queue._queue_reply(  # noqa: SLF001
        business_db, scope, conversation, "Your problems", "pi-board:test", {"visual": "board"}
    )
    text = await brain_visual_queue._queue_reply(  # noqa: SLF001
        business_db, scope, conversation, "Here is the list.", "pi-text:test", {}
    )
    held = await brain_visual_queue.attach_map(
        business_db, scope, settings, conversation, [board, text], "en", asked=True
    )
    assert held == [board, text]  # one picture a turn: the board went, the map waits
    again = await brain_visual_queue.attach_map(
        business_db, scope, settings, conversation, [text], "en", asked=True
    )
    assert len(again) == 2 and again[0] == text  # without the board the map goes after the text
    picture = await business_db.get(PiMessage, again[1])
    assert picture.media["visual"] == "map"
    await pi.close()


async def test_asking_for_the_map_when_the_summary_is_due_skips_the_board(
    api, business_db, monkeypatch
):
    from app.modules.pi import brain_visual_queue

    boards = []
    real = brain_visual_queue.attach_board

    async def spy(*args, **kwargs):
        boards.append(1)
        return await real(*args, **kwargs)

    monkeypatch.setattr(brain_visual_queue, "attach_board", spy)
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await enable(api)
    await say(pi, FIRST, "md-4")
    # the turn would show the sorted summary and its board: asked for the map, the board is skipped
    from app.modules.pi import service_conversation

    real_summary = service_conversation.brain_summary

    def summary_now(turn, context):
        real_summary(turn, context)
        turn._summary = True  # noqa: SLF001

    monkeypatch.setattr(service_conversation, "brain_summary", summary_now)
    await say(pi, "show me the naqsha of my problems", "md-5")
    assert boards == []
    await pi.close()


# --- the buttons and the pictures per cluster ----------


THINGS = [
    ("Old stock is stuck", "purana maal ruka hai", "stock_inventory"),
    ("Cash is tied up", "paisa phansa hai", "cash_collections"),
    ("Suppliers paid late", "suppliers ko late payment", "suppliers_purchasing"),
    ("Staff come late", "staff der se aata hai", "people_hr"),
    ("Customers wait long", "customer intezar karta hai", "customer_experience_digital"),
    ("Prices change daily", "rates roz badalte hain", "sales_marketing"),
    ("Shop rent is high", "kiraya bohat zyada hai", "finance_admin"),
    ("Deliveries go missing", "delivery gum ho jati hai", "operations_delivery"),
    ("Bills are lost", "bills kho jate hain", "finance_admin"),
    ("Shelves are untidy", "shelves bikhri hui hain", "operations_delivery"),
    ("No sales record", "sales ka record nahi", "finance_admin"),
    ("Power cuts hurt", "bijli chali jati hai", "operations_delivery"),
]


def twelve(context, n):
    ops = [create(title, words, category) for title, words, category in THINGS]
    return turn(
        reply=f"{OPENING} Noted all of them. Anything else?", language="en", problem_ops=ops
    )


async def test_more_than_nine_problems_go_as_an_overview_and_cluster_pictures_question_last(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, twelve)
    pi = await workspace(api, business_db)
    await enable(api)
    await say(pi, "twelve things are going wrong in the shop, all at once, really", "mc-1")
    shared = await maps(business_db)
    assert len(shared) >= 3  # the overview and a picture per cluster
    assert len(shared) <= 5
    assert all(m.media["visual"] == "map" for m in shared)
    assert [m.body.count("?") for m in shared] == [0] * (len(shared) - 1) + [1]
    assert shared[-1].body.endswith("Are the links right?")
    links = [
        m["interactive"]["header"]["image"]["link"]
        if m["type"] == "interactive"
        else m["image"]["link"]
        for m in pi.sent
        if m["type"] in ("interactive", "image")
    ]
    assert len(links) == len(shared) and len(set(links)) == len(links)
    for link in links:  # every picture is its own link and really a picture
        got = await api.get(served(pi, link))
        assert got.status_code == 200 and got.content[:8] == b"\x89PNG\r\n\x1a\n"
    [last] = [m for m in pi.sent if m["type"] == "interactive"]
    assert len(last["interactive"]["action"]["buttons"]) == 3
    one = [m for m in pi.sent if m["type"] == "image"]
    assert len(one) == len(shared) - 1
    # a part that does not exist is not served
    token = brain_visuals.token(
        api._transport.app.state.settings,
        (await pi.conversation()).id,
        "map",
        "en",
        version=1,
        part=7,
    )
    missing = await api.get(
        served(pi, brain_visuals.url(api._transport.app.state.settings, token, "map"))
    )
    assert missing.status_code == 404
    await pi.close()


async def test_a_new_version_keeps_the_nodes_where_the_owner_saw_them(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await enable(api)
    await say(pi, FIRST, "mp-1")
    conversation = await pi.conversation()
    [one] = (await business_db.scalars(select(PiMapVersion))).all()
    assert one.positions and set(one.positions) == {"P1", "P2", "P3"}  # stored when it was shared
    seen = dict(one.positions)
    scope = scope_of(conversation)
    first = await business_db.scalar(select(PiProblem).where(PiProblem.number == 1))
    first.status = "parked"
    await note(business_db, conversation, 4, "naya masla")
    two, changed = await map_builder.save_if_changed(business_db, scope, conversation.customer_id)
    assert changed and two.version == 2 and two.positions == {}
    settings = api._transport.app.state.settings
    token = brain_visuals.token(settings, conversation.id, "map", "en", version=2)
    got = await api.get(served(pi, brain_visuals.url(settings, token, "map")))
    assert got.status_code == 200
    await business_db.refresh(two)
    assert {k: two.positions[k] for k in seen} == seen  # nobody moved
    assert two.positions["P4"] not in seen.values()
    again = await api.get(served(pi, brain_visuals.url(settings, token, "map")))
    assert again.content == got.content  # drawn the same every time it is fetched
    await pi.close()


# --- the quiet-owner follow-up (decision 6) ----------

MAP_TEMPLATE = {"followup_templates": {"en": {"map": {"name": "map_nudge", "language": "en"}}}}


async def quiet_chat(api, db, monkeypatch, days=4, **brief):
    adaptive(monkeypatch, model)
    pi = await workspace(api, db)
    await enable(api)
    await say(pi, FIRST, "mf-1")
    conversation = await pi.conversation()
    await db.refresh(conversation)
    conversation.service_brief = {
        **(conversation.service_brief or {}),
        "reminder_consent": "granted",
        **brief,
    }
    conversation.last_inbound_at = datetime.now(UTC) - timedelta(days=days)
    await configure(db, pi, **MAP_TEMPLATE)
    return pi, conversation


async def map_followups(db):
    rows = await db.scalars(select(PiMessage).where(PiMessage.direction == "outbound"))
    return [m for m in rows if ((m.media or {}).get("followup") or {}).get("kind") == "map"]


async def test_a_quiet_owner_gets_two_map_template_follow_ups_spaced_out_then_nothing(
    api, business_db, monkeypatch
):
    pi, conversation = await quiet_chat(api, business_db, monkeypatch)
    [queued] = await brain_followups.sweep(pi.ctx)
    message = await business_db.get(PiMessage, queued)
    assert message.media["ladder"]["template"] == {"name": "map_nudge", "language": "en"}
    assert message.media["followup"] == {"kind": "map", "step": 1}
    assert await brain_followups.sweep(pi.ctx) == []  # the second is due at ten days
    week = datetime.now(UTC) + timedelta(days=7)  # eleven days since they wrote
    [second] = await brain_followups.sweep(pi.ctx, now=week)
    assert (await business_db.get(PiMessage, second)).media["followup"]["step"] == 2
    later = datetime.now(UTC) + timedelta(days=40)
    assert await brain_followups.sweep(pi.ctx, now=later) == []  # two, spaced out, then stop
    await business_db.refresh(conversation)
    assert conversation.service_brief["map_followups"]["total"] == 2
    # the owner writes again: a new quiet spell starts counting from zero, the total stays
    assert brain_followups.map_followups(conversation)[1] == 2
    await pi.close()


async def test_no_map_follow_up_without_consent_a_template_stop_a_decline_or_the_flag(
    api, business_db, monkeypatch
):
    pi, conversation = await quiet_chat(api, business_db, monkeypatch, reminder_consent="unknown")
    assert await brain_followups.sweep(pi.ctx) == []  # a template needs the owner's agreement
    for brief, state in (
        ({"reminder_consent": "declined"}, None),  # stop is honoured
        ({"reminder_consent": "granted"}, "S5b_DECLINED"),  # after a decline: nothing
        ({"reminder_consent": "granted"}, "X_HUMAN"),
        (
            {
                "reminder_consent": "granted",
                "customer_waiting_until": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            },
            None,
        ),  # "remind me later"
    ):
        conversation.service_brief = {**conversation.service_brief, **brief}
        conversation.flow_state = state or "S1_LISTENING"
        await business_db.flush()
        assert await brain_followups.sweep(pi.ctx) == [], (brief, state)
    conversation.service_brief = {"reminder_consent": "granted"}
    conversation.flow_state = "S1_LISTENING"
    await disable(api)  # the flag is off: other workspaces are untouched
    assert await brain_followups.sweep(pi.ctx) == []
    assert await map_followups(business_db) == []
    await pi.close()


async def test_a_missing_map_template_tells_staff_and_sends_nothing(api, business_db, monkeypatch):
    from app.modules.notifications.models import Notification
    from app.modules.pi.configuration import settings_row

    pi, conversation = await quiet_chat(api, business_db, monkeypatch)
    settings = await settings_row(business_db, pi.scope())
    settings.whatsapp_config = {**settings.whatsapp_config, "followup_templates": {}}
    await business_db.flush()
    assert await brain_followups.sweep(pi.ctx) == []
    titles = [n.title for n in await business_db.scalars(select(Notification))]
    assert "pi needs an approved WhatsApp template for a follow-up" in titles
    await pi.close()


async def test_the_map_follow_up_waits_out_quiet_hours(api, business_db, monkeypatch):
    pi, conversation = await quiet_chat(api, business_db, monkeypatch)
    soon = datetime.now(UTC) + timedelta(hours=5)
    monkeypatch.setattr(brain_followups, "quiet_until", lambda *a, **k: soon)
    assert await brain_followups.sweep(pi.ctx) == []
    monkeypatch.setattr(brain_followups, "quiet_until", lambda *a, **k: None)
    assert len(await brain_followups.sweep(pi.ctx)) == 1
    await pi.close()


# --- pi tells what changed after a dashboard edit (4.9) ----------


async def test_a_dashboard_edit_is_noted_only_with_map_share_on(
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
    off = await customer.post(
        f"{path}/problems/P1", json={"action": "resolve"}, headers=csrf(customer)
    )
    assert off.status_code == 200
    await business_db.refresh(conversation)
    assert "map_changes" not in (conversation.service_brief or {})
    from app.modules.pi.configuration import settings_row

    row = await settings_row(business_db, scope_of(conversation))
    row.response_rules = {**row.response_rules, "pi_mode": "brain", "brain": {"map_share": True}}
    await business_db.flush()
    for action, node in (("park", "P2"), ("rename", "P2")):
        body = {"action": action, **({"label": "maal ka hisaab"} if action == "rename" else {})}
        response = await customer.post(f"{path}/problems/{node}", json=body, headers=csrf(customer))
        assert response.status_code == 200
    await business_db.refresh(conversation)
    pending = conversation.service_brief["map_changes"]
    assert pending["labels"] == ["paisa phansa", "maal ka hisaab"]
    await business.aclose()
    await customer.aclose()


async def waiting_change(api, db, monkeypatch, *, inbound_hours=1, seconds=300, **brief):
    adaptive(monkeypatch, model)
    pi = await workspace(api, db)
    await enable(api)
    await say(pi, FIRST, "mx-1")
    conversation = await pi.conversation()
    await db.refresh(conversation)
    changed = map_share.note_dashboard_change(
        {**(conversation.service_brief or {}), **brief}, "purana maal ruka hai", datetime.now(UTC)
    )
    changed["map_changes"]["at"] = (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat()
    conversation.service_brief = changed
    conversation.last_inbound_at = datetime.now(UTC) - timedelta(hours=inbound_hours)
    await db.flush()
    return pi, conversation


async def test_pi_tells_what_changed_in_one_short_line_with_no_question(
    api, business_db, monkeypatch
):
    pi, conversation = await waiting_change(api, business_db, monkeypatch)
    [queued] = await brain_followups.sweep(pi.ctx)
    message = await business_db.get(PiMessage, queued)
    assert message.body == (
        "I saw the changes you made to your map (purana maal ruka hai). My notes now match."
    )
    assert message.sender_type == "ai" and message.media == {"map_change": True}
    await business_db.refresh(conversation)
    assert "map_changes" not in conversation.service_brief  # told once
    assert await brain_followups.sweep(pi.ctx) == []
    await pi.close()


async def test_the_changed_line_waits_for_the_burst_the_hour_and_quiet_hours(
    api, business_db, monkeypatch
):
    pi, conversation = await waiting_change(api, business_db, monkeypatch, seconds=30)
    assert await brain_followups.sweep(pi.ctx) == []  # edits may still be coming
    assert "map_changes" in conversation.service_brief
    conversation.service_brief = {
        **conversation.service_brief,
        "map_changes": {
            **conversation.service_brief["map_changes"],
            "at": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
        },
        "map_changes_told_at": (datetime.now(UTC) - timedelta(minutes=20)).isoformat(),
    }
    await business_db.flush()
    assert await brain_followups.sweep(pi.ctx) == []  # at most one line an hour
    assert "map_changes" in conversation.service_brief  # kept for later
    conversation.service_brief = {
        **conversation.service_brief,
        "map_changes_told_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
    }
    await business_db.flush()
    monkeypatch.setattr(
        brain_followups, "quiet_until", lambda *a, **k: datetime.now(UTC) + timedelta(hours=2)
    )
    assert await brain_followups.sweep(pi.ctx) == []  # never at night
    monkeypatch.setattr(brain_followups, "quiet_until", lambda *a, **k: None)
    assert len(await brain_followups.sweep(pi.ctx)) == 1
    await pi.close()


async def test_outside_the_24_hour_window_the_change_is_dropped_not_sent_as_a_template(
    api, business_db, monkeypatch
):
    pi, conversation = await waiting_change(api, business_db, monkeypatch, inbound_hours=30)
    assert await brain_followups.sweep(pi.ctx) == []
    await business_db.refresh(conversation)
    assert "map_changes" not in conversation.service_brief
    sent = [m for m in await pi.outbound() if (m.media or {}).get("map_change")]
    assert sent == []
    await pi.close()


async def test_the_changed_line_is_in_the_owners_language(api, business_db, monkeypatch):
    pi, conversation = await waiting_change(api, business_db, monkeypatch)
    conversation.language = "es"
    await business_db.flush()
    [queued] = await brain_followups.sweep(pi.ctx)
    assert (await business_db.get(PiMessage, queued)).body == (
        "Vi los cambios que hiciste en tu mapa (purana maal ruka hai). Mis notas ya coinciden."
    )
    await pi.close()


async def test_other_workspaces_are_untouched_when_map_share_is_off(api, business_db, monkeypatch):
    pi, conversation = await waiting_change(api, business_db, monkeypatch)
    await disable(api)
    assert await brain_followups.sweep(pi.ctx) == []
    sent = [m for m in await pi.outbound() if (m.media or {}).get("map_change")]
    assert sent == []
    await pi.close()
