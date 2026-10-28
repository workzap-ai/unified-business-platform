"""What pi understood when it sent a message is shown to the team, whitelisted and redacted."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.modules.pi import message_understood as mu
from app.modules.pi.schemas import MessageView


def message_view(understood):
    return MessageView.model_validate(
        {
            "id": uuid4(),
            "conversation_id": uuid4(),
            "direction": "outbound",
            "sender_type": "ai",
            "message_type": "text",
            "body": "Kya stock ka hisaab rehta hai?",
            "media": {},
            "status": "sent",
            "error_code": None,
            "agent_key": None,
            "sent_by_label": None,
            "created_at": datetime.now(UTC),
            "understood": understood,
        }
    )


def test_only_named_keys_leave_the_server() -> None:
    v = message_view(
        {
            "move": "ask",
            "label": "Listening",
            "reason": "needs the size of the stock",
            "customer_name": "Sara Khan",
            "internal_prompt": "secret",
            "problems": [{"number": 2, "title": "Stock is wrong", "category": "inventory", "x": 1}],
            "hypotheses": [{"text": "Counts are not written down", "confidence": "high"}],
            "offer": {"rule": "R1", "allowed": False, "blocked_reason": "still listening"},
            "box_state": "collecting",
        }
    )
    assert v.understood is not None
    assert set(v.understood) == {
        "move",
        "label",
        "reason",
        "problems",
        "hypotheses",
        "offer",
        "box_state",
    }
    assert v.understood["problems"] == [
        {"number": 2, "title": "Stock is wrong", "category": "inventory"}
    ]


def test_texts_are_redacted_again_and_short() -> None:
    v = message_view(
        {
            "move": "ask",
            "reason": "owner wrote 4111 1111 1111 1111 and sara@example.com " + "x" * 600,
        }
    )
    assert v.understood is not None
    reason = v.understood["reason"]
    assert "4111" not in reason and "sara@example.com" not in reason
    assert len(reason) <= 300


def test_unknown_values_are_dropped_not_passed_on() -> None:
    assert mu.public_understood(None) is None
    assert mu.public_understood("text") is None
    assert mu.public_understood({"secret": "x"}) is None
    out = mu.public_understood(
        {
            "move": "ask",
            "label": "Made up",
            "hypotheses": [{"text": "A guess", "confidence": "certain"}],
            "offer": {"rule": "Z9", "allowed": True},
            "problems": [{"title": "   "}, "not a dict"],
        }
    )
    assert out == {"move": "ask", "hypotheses": [{"text": "A guess", "confidence": "low"}]}


def test_the_lists_are_capped() -> None:
    out = mu.public_understood(
        {
            "move": "summarise",
            "problems": [{"title": f"Problem {i}"} for i in range(20)],
            "hypotheses": [{"text": f"Guess {i}", "confidence": "low"} for i in range(20)],
        }
    )
    assert out is not None
    assert len(out["problems"]) == mu.MAX_PROBLEMS
    assert len(out["hypotheses"]) == mu.MAX_HYPOTHESES


def test_a_message_with_nothing_stored_has_no_annotation() -> None:
    assert message_view(None).understood is None
    assert message_view({}).understood is None


def test_each_pi_message_window_opens_at_the_owners_previous_message() -> None:
    t0 = datetime.now(UTC)

    def row(direction, sender, minutes):
        return SimpleNamespace(
            id=uuid4(),
            direction=direction,
            sender_type=sender,
            created_at=t0 + timedelta(minutes=minutes),
        )

    greeting = row("outbound", "ai", 0)
    first = row("inbound", "customer", 1)
    reply = row("outbound", "ai", 2)
    staff = row("outbound", "human", 3)
    second = row("inbound", "customer", 4)
    reply2 = row("outbound", "ai", 5)
    found = mu.windows([greeting, first, reply, staff, second, reply2])
    assert found[greeting.id] == (None, None)
    assert found[reply.id] == (first.created_at, first.id)
    assert found[reply2.id] == (second.created_at, second.id)
    assert staff.id not in found
