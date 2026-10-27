"""The pure parts of the staff review view (alerts, origin of a handoff, node status, caps)."""

import pytest

from app.modules.pi import staff_review as r


@pytest.mark.parametrize(
    ("reason", "intent", "by", "expected"),
    [
        ("customer_request", "human_request", "System", "keyword"),
        ("customer_request", "support", "System", "owner_asked"),
        ("provider_failure", None, "System", "failure"),
        ("tool_failure", None, "System", "failure"),
        ("low_confidence", None, "System", "failure"),
        ("manual", None, "Sara", "operator_review"),
        ("policy", None, "System", "policy"),
        ("sensitive", None, "System", "policy"),
    ],
)
def test_origin_of_a_handoff(reason, intent, by, expected):
    assert r.classify_origin(reason, intent, by) == expected
    assert expected in r.ORIGIN_TEXT


@pytest.mark.parametrize(
    ("status", "tags", "stale", "expected"),
    [
        ("draft", [], False, "open"),
        ("confirmed", [], False, "confirmed"),
        ("corrected", [], False, "confirmed"),
        ("in_document", [], False, "in_box"),
        ("quoted", [], False, "in_box"),
        ("parked", [], False, "parked"),
        ("draft", ["parked"], False, "parked"),
        ("resolved", [], True, "resolved"),
        ("draft", [], True, "stale"),
    ],
)
def test_node_status(status, tags, stale, expected):
    assert r.node_status(status, tags, stale) == expected


def test_a_quiet_chat_has_no_alert():
    assert (
        r.alerts_for(["stock runs out"], handoff_open=False, asks_open=0, asks_unanswered=0) == []
    )


def test_churn_is_red_and_sorts_before_everything():
    alerts = r.alerts_for(
        ["kahin aur jaun ga", "bar bar sawal", "jaldi batao"],
        handoff_open=True,
        asks_open=1,
        asks_unanswered=1,
    )
    assert [a["level"] for a in alerts] == ["red", "amber", "yellow", "blue"]
    assert r.alert_rank(alerts) == 0


def test_frustration_needs_two_signals_unless_pi_is_already_fatigued():
    once = ["how many times do i have to say it"]
    assert r.alerts_for(once, handoff_open=False, asks_open=0, asks_unanswered=0) == []
    assert (
        r.alerts_for([*once, "stop asking"], handoff_open=False, asks_open=0, asks_unanswered=0)[0][
            "key"
        ]
        == "frustration"
    )
    assert r.alerts_for(once, handoff_open=False, asks_open=0, asks_unanswered=0, fatigue=True)


def test_an_open_request_is_blue_until_it_has_waited_two_pi_turns():
    open_ = r.alerts_for([], handoff_open=False, asks_open=1, asks_unanswered=0)
    assert [(a["key"], a["level"]) for a in open_] == [("request_open", "blue")]
    late = r.alerts_for([], handoff_open=False, asks_open=1, asks_unanswered=1)
    assert [(a["key"], a["level"]) for a in late] == [("request_unanswered", "amber")]


def test_phone_is_masked_to_the_last_four_digits():
    assert r.mask_phone("+92 311 2546598") == "•••• 6598"
    assert "311" not in r.mask_phone("+923112546598")
    assert r.mask_phone(None) == "••••"


def test_owner_text_is_redacted_again_on_the_way_out():
    out = r.clean("call me on 0311 2546598 or mail ali@example.com, card 4111 1111 1111 1111")
    assert "2546598" not in out and "ali@example.com" not in out and "4111 1111" not in out


def test_idea_budget_uses_the_larger_of_chat_and_business_and_never_goes_negative():
    budget = r.idea_budget(2, {"Stock": 1}, customer_given=9)
    assert budget["per_problem_cap"] == 2 and budget["per_business_cap"] == 8
    assert budget["business_remaining"] == 0 and budget["given_for_business"] == 9
    assert r.idea_budget(3, {})["business_remaining"] == 5


def test_every_message_label_is_one_of_the_spec_labels():
    assert set(r.MOVE_LABELS.values()) <= {"Listening", "Noted", "Ideas"}
