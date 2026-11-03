"""The map share triggers beyond the first (Book 5, 4.4 and Part 6): the offer check-in, the owner
coming back, the 90-day "pichli baar ka", a real parked status, kept node positions, the wording in
the eight priority languages and the quiet-owner follow-up cadence."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest

from app.modules.pi import flow, followup_policy, map_builder, map_render, map_share, taxonomy
from app.modules.pi.fixed_lines import PRIORITY

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


def problem(number, status="confirmed", tags=(), updated=None, **kw):
    return NS(
        id=uuid4(),
        number=number,
        title=f"Problem {number}",
        title_local=kw.get("local", f"masla {number}"),
        user_words=[],
        status=status,
        tags=list(tags),
        category=kw.get("category", "stock_inventory"),
        impact={},
        since={},
        frequency={},
        scope={},
        merged_into=None,
        updated_at=updated,
    )


# --- a real parked status ----------


def test_parked_is_a_real_status_kept_out_of_the_live_set_but_drawn():
    assert "parked" in taxonomy.STATUSES
    assert "parked" not in taxonomy.ACTIVE  # not in the summaries or the counts
    assert "parked" in map_builder.DRAWN  # still on the map
    built = map_builder.build_map([problem(1), problem(2, status="parked")], [], now=NOW)
    assert [(n["id"], n["status"]) for n in built["nodes"]] == [("P1", "open"), ("P2", "parked")]


def test_the_older_parked_tag_still_reads_as_parked():
    built = map_builder.build_map([problem(1, tags=["parked"])], [], now=NOW)
    assert built["nodes"][0]["status"] == "parked"


def test_parking_changes_what_the_owner_sees_so_it_is_a_new_version():
    a = map_builder.build_map([problem(1)], [], now=NOW)
    b = map_builder.build_map([problem(1, status="parked")], [], now=NOW)
    assert a["hash"] != b["hash"]


# --- the map ages (6.4) ----------


def test_a_node_untouched_for_ninety_days_is_stale_until_touched():
    old = problem(1, updated=NOW - timedelta(days=90))
    fresh = problem(2, updated=NOW - timedelta(days=89))
    done = problem(3, status="resolved", updated=NOW - timedelta(days=200))
    unknown = problem(4)
    built = map_builder.build_map([old, fresh, done, unknown], [], now=NOW)
    assert [bool(n.get("stale")) for n in built["nodes"]] == [True, False, False, False]
    assert map_builder.stale_ids(built) == ["P1"]
    touched = problem(1, updated=NOW)
    assert "stale" not in map_builder.build_map([touched], [], now=NOW)["nodes"][0]


def test_a_stale_node_is_tagged_in_the_picture_the_text_and_the_alt_list():
    built = map_builder.build_map([problem(1, updated=NOW - timedelta(days=120))], [], now=NOW)
    plain = map_builder.build_map([problem(1, updated=NOW)], [], now=NOW)
    old = map_render.render_map(built, "roman_ur")
    new = map_render.render_map(plain, "roman_ur")
    assert old.images and old.images[0].png != new.images[0].png
    assert "Pichli baar ka" in old.images[0].alt[0]
    assert "Pichli baar ka" in old.text and "Pichli baar ka" not in new.text
    assert "From last time" in map_render.render_map(built, "en").text


def test_every_drawable_language_has_the_stale_tag():
    for lang in map_render.DRAWABLE_LANGUAGES:
        assert map_render.TEXT[lang]["stale"]


# --- when the map goes (4.4, Part 6) ----------


def test_the_offer_check_in_is_sent_once_and_not_again_for_a_map_just_seen():
    facts = map_builder.ShareFacts(nodes=4, hurried=True, at_offer=True)
    assert map_builder.share_due(facts) == (True, "offer")
    seen = map_builder.ShareFacts(
        nodes=4, at_offer=True, ever_shared=True, changed_since_share=False
    )
    assert map_builder.share_due(seen) == (False, "offer_seen")


def test_a_return_shares_the_map_even_under_the_six_message_limit_and_never_when_empty():
    back = map_builder.ShareFacts(
        nodes=2, ever_shared=True, pi_messages_since_share=1, returning=True
    )
    assert map_builder.share_due(back) == (True, "return")
    assert map_builder.share_due(map_builder.ShareFacts(nodes=0, returning=True)) == (
        False,
        "empty",
    )
    quiet = map_builder.ShareFacts(nodes=2, ever_shared=True, pi_messages_since_share=1)
    assert map_builder.share_due(quiet)[0] is False


def test_a_return_is_a_day_or_more_after_the_last_message():
    assert not map_share.is_return(None, NOW)
    assert not map_share.is_return(NOW - timedelta(hours=23), NOW)
    assert map_share.is_return(NOW - timedelta(days=1), NOW)
    assert map_share.is_return((NOW - timedelta(days=3)).replace(tzinfo=None), NOW)
    rows = [
        NS(direction="outbound", created_at=NOW - timedelta(hours=1)),
        NS(direction="inbound", created_at=NOW - timedelta(days=2)),
    ]
    assert map_share.returning(rows, NS(created_at=NOW))  # the outbound one does not count
    assert not map_share.returning([], NS(created_at=NOW))  # a first message is not a return


def test_the_returning_state_is_reachable_from_listening_and_leaves_on_the_next_turn():
    for state in flow.RETURNABLE:
        assert flow.advance(state, flow.State.S_RETURN) == flow.State.S_RETURN
    for state in (flow.State.S5B_DECLINED, flow.State.S9B_DECLINED_QUOTE, flow.State.S7_DELIVERED):
        assert state not in flow.RETURNABLE  # a decline and a quote keep their own state
    assert flow.after_turn(flow.State.S_RETURN, asked_question=False) == flow.State.S1_LISTENING
    assert flow.after_turn(flow.State.S_RETURN, asked_question=True) == flow.State.S2_CLARIFYING
    assert flow.after_turn(flow.State.S_RETURN, asked_question=False, noted=True) == (
        flow.State.S3_NOTED
    )
    assert (
        "no question" in flow.GUIDANCE[flow.State.S_RETURN]
        or "ask no question" in (flow.GUIDANCE[flow.State.S_RETURN])
    )


# --- the words, in the eight priority languages ----------


def test_every_priority_language_has_every_line_and_every_button_fits():
    assert map_share.titles_ok()
    assert set(PRIORITY) == set(map_share.QUESTIONS) == set(map_share.BUTTONS)
    for language in PRIORITY:
        assert len(map_share.buttons(language)) == 3
        assert all(len(t) <= 20 for t in map_share.buttons(language))
        assert len({map_share.question(language, n) for n in range(3)}) == 3


def test_the_question_rotates_and_unknown_languages_get_english():
    assert [map_share.question("en", n) for n in range(4)] == [
        "Are the links right?",
        "Is anything missing?",
        "Which one comes first?",
        "Are the links right?",
    ]
    assert map_share.question("roman_ur", 0) == "Kya ye jorr sahi hain?"
    assert map_share.question("sw", 0) == "Are the links right?"
    assert map_share.question(None) == "Are the links right?"
    assert map_share.question("fr-CA", 1) == "Manque-t-il quelque chose ?"


def question_marks(text):
    return text.count("?") + text.count("؟")


@pytest.mark.parametrize("language", PRIORITY)
def test_the_return_text_has_one_question_and_it_is_the_last_sentence(language):
    text = map_share.return_text(language, stale=True, link="https://pi.example/customer")
    assert question_marks(text) == 1
    assert text.rstrip().endswith(("?", "؟"))
    assert "https://pi.example/customer" in text
    plain = map_share.return_text(language, stale=False)
    assert question_marks(plain) == 1 and "https://" not in plain
    assert len(plain) < len(text)  # the line about old problems comes only when some are old


def test_the_return_text_in_roman_urdu_is_the_spec_wording():
    text = map_share.return_text("roman_ur", stale=False)
    assert text.startswith("Wapas aaye, achha laga. Pichli baar ka naqsha ye raha.")
    assert text.endswith("Us ke baad kuch badla, ya koi naya masla aaya?")


@pytest.mark.parametrize("language", PRIORITY)
def test_the_changed_line_is_one_short_statement_with_no_question_and_the_owners_words(language):
    line = map_share.changed_line(language, ["maal ruka", "paisa phansa", "late", "fourth"])
    assert "maal ruka" in line and "paisa phansa" in line and "late" in line
    assert "fourth" not in line  # at most three
    assert question_marks(line) == 0 and "\n" not in line and len(line) < 160


@pytest.mark.parametrize("language", PRIORITY)
def test_the_follow_up_is_calm_and_never_mentions_the_box_or_pressure(language):
    text = map_share.followup_text(language)
    assert question_marks(text) == 0
    lowered = text.lower()
    assert not any(word in lowered for word in followup_policy.PRESSURE)
    assert "box" not in lowered and "quote" not in lowered


def test_a_dashboard_edit_is_remembered_once_per_label_and_capped():
    brief = {"keep": 1}
    for label in ("a", "b", "a", "c", "d"):
        brief = map_share.note_dashboard_change(brief, label, NOW)
    assert brief["keep"] == 1
    assert brief["map_changes"]["labels"] == ["a", "b", "c"]
    assert brief["map_changes"]["at"] == NOW.isoformat()


def test_the_dashboard_link_is_the_customer_page_or_nothing():
    assert map_share.dashboard_link("https://pi.example/") == "https://pi.example/customer"
    assert map_share.dashboard_link("") == ""


# --- positions the owner saw ----------


def test_positions_are_stored_once_and_read_back_as_slots():
    row = NS(positions={})
    map_builder.remember_positions(row, {"P1": (0, 1), "P2": (1, 0)})
    assert row.positions == {"P1": [0, 1], "P2": [1, 0]}
    map_builder.remember_positions(row, {"P1": (5, 5)})  # what the owner saw does not move
    assert row.positions["P1"] == [0, 1]
    assert map_builder.slots_of(row.positions) == {"P1": (0, 1), "P2": (1, 0)}
    assert map_builder.slots_of({"P1": "x", "P2": [1], "P3": ["a", 1], "P4": [2, 1]}) == {
        "P4": (2, 1)
    }
    assert map_builder.slots_of(None) == {}


def test_a_new_version_keeps_the_nodes_where_the_owner_saw_them():
    first = map_builder.build_map([problem(1), problem(2), problem(3)], [], version=1, now=NOW)
    drawn = map_render.render_map(first, "en")
    seen = drawn.positions
    assert set(seen) == {"P1", "P2", "P3"}
    # the owner parks the first problem and a new one arrives: the others do not move
    second = map_builder.build_map(
        [problem(1, status="parked"), problem(2), problem(3), problem(4)],
        [],
        version=2,
        previous=first,
        now=NOW,
    )
    kept = map_render.render_map(second, "en", previous=seen).positions
    assert {k: kept[k] for k in seen} == seen
    assert kept["P4"] not in seen.values()


# --- more than nine problems ----------


def big_map(count):
    nodes = [
        {
            "id": f"P{i}",
            "label": f"maal {i}",
            "facts": [],
            "category": "stock_inventory",
            "status": "open",
            "is_new": False,
        }
        for i in range(1, count + 1)
    ]
    links = [
        {
            "from": f"P{i}",
            "to": f"P{i + 1}",
            "type": "causes",
            "label": "",
            "evidence": "owner_said",
        }
        for i in (1, 2, 5, 6, 8, 9)
        if i < count
    ]
    return {
        "version": 1,
        "nodes": nodes,
        "links": links,
        "clusters": map_builder.clusters_of(nodes, links),
    }


def test_a_map_with_more_than_nine_problems_is_an_overview_and_a_picture_per_cluster():
    drawn = map_render.render_map(big_map(12), "en")
    kinds = [image.kind for image in drawn.images]
    assert kinds[0] == "overview" and kinds.count("overview") == 1
    assert kinds.count("detail") >= 2
    assert all(image.png[:8] == b"\x89PNG\r\n\x1a\n" for image in drawn.images)
    small = map_render.render_map(big_map(9), "en")
    assert [image.kind for image in small.images] == ["map"]


# --- the quiet-owner follow-up (decision 6) ----------


def chat(**kw):
    base = {
        "state": flow.State.S1_LISTENING,
        "last_inbound_at": NOW - timedelta(days=4),
        "sent": {},
        "has_map": True,
    }
    return followup_policy.Chat(**{**base, **kw})


def test_a_quiet_owner_gets_a_small_number_of_map_follow_ups_spaced_out_then_nothing():
    assert (
        followup_policy.next_map_followup(chat(last_inbound_at=NOW - timedelta(days=2)), NOW)
        is None
    )
    first = followup_policy.next_map_followup(chat(), NOW)
    assert first is not None and first.kind == "map" and first.needs_template
    assert first.at == NOW - timedelta(days=1)  # day 3 after their last message
    quiet = chat(last_inbound_at=NOW - timedelta(days=8), map_sent=1)
    assert followup_policy.next_map_followup(quiet, NOW) is None  # the second is at day 10
    second = chat(last_inbound_at=NOW - timedelta(days=11), map_sent=1)
    assert followup_policy.next_map_followup(second, NOW) is not None
    done = chat(last_inbound_at=NOW - timedelta(days=30), map_sent=2)
    assert followup_policy.next_map_followup(done, NOW) is None  # then stop
    lifetime = chat(map_total=map_share.FOLLOWUP_LIFETIME)
    assert followup_policy.next_map_followup(lifetime, NOW) is None


@pytest.mark.parametrize(
    "state",
    [
        flow.State.S5B_DECLINED,  # after a decline: nothing
        flow.State.S9B_DECLINED_QUOTE,
        flow.State.S5_READINESS,  # the offer is open: its own rules
        flow.State.S7_DELIVERED,
        flow.State.X_HUMAN,  # a person has the chat
        flow.State.X_PAUSED,
        flow.State.X_BLOCKED,
        flow.State.X_EMERGENCY,
        flow.State.S_HOLD,  # something heavy: no follow-up
    ],
)
def test_no_map_follow_up_after_a_decline_in_a_quote_or_in_an_exception(state):
    assert followup_policy.next_map_followup(chat(state=state), NOW) is None


def test_no_map_follow_up_after_stop_or_without_a_map():
    assert followup_policy.next_map_followup(chat(opted_out=True), NOW) is None
    assert followup_policy.next_map_followup(chat(has_map=False), NOW) is None


def test_the_map_follow_up_text_is_in_the_policy_table_and_clear_of_pressure():
    for language in ("en", "roman_ur"):
        text = followup_policy.text_for("map", language)
        assert text == map_share.followup_text(language)
        assert not any(word in text.lower() for word in followup_policy.PRESSURE)
