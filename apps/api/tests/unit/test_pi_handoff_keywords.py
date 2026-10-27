"""A handoff keyword hands the chat to staff only when the owner asks for someone (live chat,
2026-10-27: "accounts wala banda baar baar phone karta hai" matched the keyword "banda")."""

from types import SimpleNamespace

import pytest

from app.modules.pi.runtime import _keyword_handoff
from app.modules.pi.service_conversation import ServiceTurn, needs_person

POLICY = SimpleNamespace(
    handoff_rules={
        "keywords": [
            "human",
            "representative",
            "person",
            "founder",
            "insaan",
            "banda",
            "team se baat",
        ]
    }
)
SCHOOL = (
    "Mera school Faisalabad mein hai, 600 bachay hain. Fee time par nahi aati, har mahine 80 se "
    "zyada parents late hote hain. Accounts wala banda baar baar phone karta hai magar koi asar "
    "nahi hota."
)


def test_a_business_problem_that_says_banda_is_not_a_handoff() -> None:
    assert not _keyword_handoff(POLICY, SCHOOL)
    assert not _keyword_handoff(POLICY, "Mera banda kaam nahi karta, chori ka shak hai, kya karoon")
    assert not _keyword_handoff(POLICY, "personal loan ka kaam hai mera")


@pytest.mark.parametrize(
    "said",
    [
        "human",
        "I want to talk to a human",
        "can I speak to a person please",
        "mujhe insaan se baat karni hai",
        "kisi banda se baat karni hai",
        "team se baat karwao",
    ],
)
def test_a_real_request_for_a_person_still_hands_over(said: str) -> None:
    assert _keyword_handoff(POLICY, said)


def test_a_long_message_needs_a_request_in_it() -> None:
    long_message = (
        "the person at the counter is rude and sales have dropped a lot this month because of it"
    )
    assert not _keyword_handoff(POLICY, long_message)
    assert _keyword_handoff(POLICY, long_message + ", I need to talk to someone about it")


def test_the_model_guess_of_wants_person_is_not_enough_when_staff_phone_people() -> None:
    turn = ServiceTurn(reply="x", wants_person=True)
    assert not needs_person(turn, {"latest_customer_message": SCHOOL})
    assert needs_person(turn, {"latest_customer_message": "mujhe kisi se baat karni hai"})
