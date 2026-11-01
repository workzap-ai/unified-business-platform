"""RPRIV06 / RT16 (platform spec v1.6): "delete everything you know about me" in the chat is
acknowledged to the owner and handed to staff. The chat NEVER erases: a staff member approves in
the console (brain_erase_routes, confirm), so a message cannot wipe records by itself."""

from pathlib import Path

import pytest

from app.modules.pi import safety
from app.modules.pi import service_conversation as sc


@pytest.mark.parametrize(
    "said",
    [
        "Delete everything you know about me",
        "please erase all my data",
        "mere data delete karo",
        "mera data delete kar do",
        "meri information delete kar do",
        "mere records mita do",
        "mera sab data hata do",
        "sab kuch mita do",
        "data delete karo",
        "delete my account",
        "میرا ڈیٹا حذف کر دیں",
        "احذف بياناتي",
    ],
)
def test_a_deletion_request_in_any_of_these_words_is_caught(said: str) -> None:
    assert safety.boundary_asked(said) == safety.Boundary.DELETION


@pytest.mark.parametrize(
    "said",
    ["data bhej do", "delete the last message", "mera data kaisa hai", "I will delete the file"],
)
def test_ordinary_talk_is_not_a_deletion_request(said: str) -> None:
    assert safety.boundary_asked(said) != safety.Boundary.DELETION


def test_the_owner_gets_an_acknowledgement_and_staff_get_the_request_not_an_erase() -> None:
    context = {
        "pi_mode": "brain",
        "latest_customer_message": "mere data delete karo",
        "reply_language": "roman_ur",
        "history": [{"role": "ai", "text": "Hi, main pi hoon, Workzap ka AI."}],
    }
    turn = sc.brain_safety(context)
    assert turn is not None and "Workzap ki team" in turn.reply
    decision = turn._decision
    assert decision.effects == ["deletion_request"]  # a ticket, nothing else
    assert "erase" not in " ".join(decision.effects)


def test_the_ticket_says_nothing_is_erased_until_staff_approve() -> None:
    text = sc.escalation_question("deletion_request")
    assert "DELETE MY DATA" in text and "Nothing has been erased" in text
    assert "approve" in text.lower()


def test_no_chat_code_path_erases_by_itself() -> None:
    root = Path(sc.__file__).parent
    for name in ("service_conversation.py", "runtime.py", "safety.py", "safety_guard.py"):
        source = (root / name).read_text(encoding="utf8")
        assert "erase_customer" not in source, name
