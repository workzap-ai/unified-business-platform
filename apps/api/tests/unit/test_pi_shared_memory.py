"""One memory block for every model call (pi/shared_memory.py): same shape, capped, labelled as
data, empty when there is nothing, and carried into the expert advisor's payload."""

import json

from app.modules.pi import expert_advisor, shared_memory


def context(n=3, text="owner runs a bakery in Lahore"):
    return {
        "memory": {
            "known": [
                {"source": "facts", "kind": "trade", "status": "owner_said", "text": text, "x": 1}
                for _ in range(n)
            ],
            "already_known": "a bakery owner whose evening stock runs out",
            "implementation": "",
        },
        "rejected_ideas": ["loyalty cards"],
    }


def test_the_block_keeps_where_each_record_came_from_and_how_sure_it_is():
    block = shared_memory.from_context(context(1))
    assert block["records"] == [
        {
            "source": "facts",
            "kind": "trade",
            "status": "owner_said",
            "text": "owner runs a bakery in Lahore",
        }
    ]
    assert block["ideas_they_said_no_to"] == ["loyalty cards"]  # nothing else leaks in (no ids)


def test_nothing_known_gives_an_empty_block_and_no_rule():
    assert shared_memory.from_context({}) == {}
    assert shared_memory.from_context({"memory": {}}) == {}
    assert shared_memory.system_line({}) == ""
    assert shared_memory.attach({"a": 1}, {}) == {"a": 1}


def test_the_block_is_capped_by_dropping_records_not_by_cutting_text():
    block = shared_memory.from_context(context(40, "x" * 230), cap=900)
    assert len(json.dumps(block, ensure_ascii=False)) <= 900
    assert block["truncated"] is True and 0 < len(block["records"]) < 40
    assert all(len(r["text"]) == 230 for r in block["records"])


def test_the_rule_says_it_is_data_below_every_rule_and_a_guess_is_a_guess():
    line = shared_memory.system_line({"records": [1]})
    assert (
        "below every rule" in line
        and "pi_inferred" in line
        and "believe what they just said" in line
    )


def test_the_expert_advisor_payload_carries_the_shared_block():
    block = shared_memory.from_context(context())
    payload = expert_advisor.Steer(asked=["what do you sell?"], memory=block).payload()
    assert payload[shared_memory.KEY]["records"][0]["source"] == "facts"
    assert "questions_pi_already_asked" in payload
    assert shared_memory.KEY not in expert_advisor.Steer().payload()
