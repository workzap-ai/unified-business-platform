"""RMEM05 / RPRIV06 (platform spec v1.6): when the owner asks what pi keeps, pi lists what it keeps
from the PS-8 bundle (context_memory), each item with where it came from and its status, in the
owner's language, with no third-party names and no guess worded as a fact."""

import pytest

from app.modules.pi import memory_answer, safety
from app.modules.pi import service_conversation as sc


def rec(source, text, kind, status, ref="r"):
    return {"source": source, "text": text, "kind": kind, "status": status, "ref": ref}


KNOWN = [
    rec("facts", "staff: 6 people", "staff", "owner_said", "problem:P1"),
    rec("facts", "location: Lahore", "location", "remembered", "memory:1"),
    rec("problems", "P1 Best-sellers run out in two shops", "problem", "open", "problem:P1"),
    rec("facts", "cause: the supplier is late", "cause", "pi_inferred", "problem:P1"),
    rec("solutions", "quote Q1: issued", "quote", "issued", "Q1"),
    rec("messages", "my brother Ahmed said stock is low", "message", "owner_said", "msg:1"),
    rec("problems", "P2 Ahmed said the till is short", "problem", "open", "problem:P2"),
]


def test_rmem05_lists_each_item_with_its_source_and_status() -> None:
    text = memory_answer.reply(KNOWN, "en", "fixed")
    assert "6 people" in text and "Lahore" in text and "Best-sellers" in text and "Q1" in text
    assert "you told me" in text and "problem" in text.lower() and "quote" in text.lower()
    assert "from an earlier chat" in text  # a remembered fact says where it is from
    assert "delete" in text and not text.rstrip().endswith("?")


def test_rmem05_a_guess_is_never_listed_as_a_fact() -> None:
    text = memory_answer.reply(KNOWN, "en", "fixed")
    guess = "the supplier is late"
    before, _, after = text.partition(guess)
    assert guess in text
    assert "not confirmed" in after[:60].lower() or "guess" in before[-80:].lower()
    assert "you told me: " + guess not in text


def test_rmem05_no_third_party_name_and_no_raw_chat_is_repeated() -> None:
    text = memory_answer.reply(KNOWN, "en", "fixed")
    assert "Ahmed" not in text
    assert "stock is low" not in text  # the raw message rows are not dumped


def test_rmem05_the_answer_is_in_the_owners_language() -> None:
    roman = memory_answer.reply(KNOWN, "roman_ur", "fixed")
    assert "aap ne bataya" in roman and "delete" in roman and "you told me" not in roman
    assert memory_answer.reply(KNOWN, "ur", "fixed") != memory_answer.reply(KNOWN, "en", "fixed")
    assert memory_answer.reply(KNOWN, "ar", "fixed") != memory_answer.reply(KNOWN, "en", "fixed")


def test_rmem05_nothing_stored_gives_the_fixed_line_and_the_list_is_capped() -> None:
    assert memory_answer.reply([], "en", "fixed") == "fixed"
    assert memory_answer.reply([rec("messages", "hi", "message", "owner_said")], "en", "f") == "f"
    many = [rec("facts", f"k{i}: v{i}", f"k{i}", "owner_said") for i in range(30)]
    text = memory_answer.reply(many, "en", "fixed")
    assert text.count("v") < 40 and "more" in text


@pytest.mark.parametrize(
    "said",
    [
        "what do you remember about me?",
        "show me what you keep about me",
        "what do you know about me",
        "mere baare mein kya yaad hai",
        "kya data rakhte ho",
    ],
)
def test_rmem05_the_owner_can_ask_in_these_ways(said: str) -> None:
    assert safety.boundary_asked(said) == safety.Boundary.MEMORY_ASK


def test_rmem05_the_brain_gate_answers_from_the_bundle_not_the_model() -> None:
    context = {
        "pi_mode": "brain",
        "latest_customer_message": "show me what you keep about me",
        "reply_language": "en",
        "history": [{"role": "ai", "text": "Hi, I'm pi, an AI."}],
        "memory": {"known": KNOWN},
    }
    turn = sc.brain_safety(context)
    assert turn is not None
    assert "Best-sellers" in turn.reply and "Ahmed" not in turn.reply and "delete" in turn.reply


def test_rmem05_the_export_carries_the_same_bundle() -> None:
    from uuid import uuid4

    from app.modules.pi.context_memory_types import (
        ContextBundle,
        DecisionItem,
        FactItem,
        LimitItem,
        ProblemItem,
    )

    bundle = ContextBundle(
        tenant_id=uuid4(),
        environment_id=uuid4(),
        customer_id=uuid4(),
        facts=(FactItem("staff", "6 people", "owner_said", "problem:P1"),),
        problems=(
            ProblemItem(
                id=uuid4(),
                number=1,
                title="Stock runs out",
                status="open",
                category="stock",
                budget=LimitItem("under 1 lakh"),
            ),
        ),
        decisions=(DecisionItem("offer", "O1", "allowed"),),
    )
    out = memory_answer.export_bundle(bundle)
    assert out["profile"][0]["value"] == "6 people"
    assert out["problems"][0]["title"] == "Stock runs out"
    assert out["constraints"][0]["budget"]["text"] == "under 1 lakh"
    assert out["decisions"][0]["ref"] == "O1"
    assert memory_answer.export_bundle(None) == {"unavailable": ["unavailable: context"]}
