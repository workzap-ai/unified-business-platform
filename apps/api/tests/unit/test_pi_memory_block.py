"""pi's durable memory block (spec 3.10 R-MEM, R-PRIV-04, R-PRIV-06). No database."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.modules.pi import constitution as c
from app.modules.pi import memory_block as mb
from app.modules.pi import service_conversation as sc

FULL = {
    "name": "Ayesha",
    "role": "owner",
    "business_name": "Noor Bakery",
    "business_type": "bakery selling cakes and bread, with a delivery rider on bikes",
    "location": "Lahore",
    "team_size": "3 branches, 14 staff",
    "channels": "shop, Instagram, WhatsApp orders",
    "current_tools": "Excel and a paper register for stock",
    "website": "noorbakery.example",
    "goal": "know exactly what is left in each branch every evening without phoning anyone",
}


def known(**more):
    return mb.Known(facts={**FULL, **more.pop("facts", {})}, **more)


def test_block_is_empty_when_nothing_is_known():
    assert mb.build(mb.Known()) == {}


def test_block_never_exceeds_its_cap_and_keeps_the_priority_order():
    block = mb.build(
        known(prefs={"language": "roman_ur", "voice_notes": "yes"}, last_time="x " * 200),
        ["role"],
    )
    assert len(json.dumps(block, ensure_ascii=False)) <= mb.BLOCK_CHARS
    keys = list(block)
    assert keys[:2] == ["name", "role"]
    assert keys.index("business_name") < keys.index("location")


def test_a_tiny_cap_still_keeps_the_most_important_facts_first():
    block = mb.build(known(), cap=120)
    assert len(json.dumps(block, ensure_ascii=False)) <= 120
    assert list(block)[:2] == ["name", "role"]


def test_already_asked_lists_only_what_is_still_unknown():
    block = mb.build(mb.Known(facts={"name": "Ayesha"}), ["name", "location", "location"])
    assert block["already_asked"] == ["location"]


def test_last_time_comes_last_so_it_is_the_first_thing_dropped():
    block = mb.build(
        mb.Known(facts={"name": "Ayesha"}, last_time="stock never matches in two branches")
    )
    assert list(block)[-1] == "last_time"


@pytest.mark.parametrize(
    "key,value",
    [
        ("name", "WhatsApp User"),
        ("name", "+92 300 1234567"),
        ("name", "Ayesha 1234"),
        ("location", "call me on 0300 1234567"),
        ("business_name", "card 4111 1111 1111 1111"),
        ("goal", "mail ali@example.com"),
        ("goal", ""),
        ("role", "unknown"),
    ],
)
def test_unsafe_or_placeholder_values_are_never_kept(key, value):
    assert mb.clean_value(key, value) is None


def test_a_third_party_named_with_a_role_keeps_only_the_role():
    kept = mb.clean_value("goal", "patient Ayesha Khan pays late")
    assert kept is not None and "Ayesha" not in kept and "patient" in kept


def test_values_are_capped_to_their_field():
    assert len(mb.clean_value("location", "Lahore " * 30) or "") <= 40


def test_row_text_roundtrips():
    assert mb.parse_row(mb.row_text("location", "Lahore")) == ("location", "Lahore")
    assert mb.parse_row("just a note") is None


def test_profile_fills_what_no_memory_row_says_and_never_overrides_it():
    state = mb.Known(facts={"location": "Karachi"})
    mb.merge_profile(state, {"location": "Lahore", "name": "Ata", "goal": "card 4111111111111111"})
    assert state.facts == {"location": "Karachi", "name": "Ata"}


@pytest.mark.parametrize(
    "reply,keys",
    [
        ("Noted. What is your name?", ["name"]),
        ("Which city are you based in? And how many staff do you have?", ["location", "team_size"]),
        ("What's your role there?", ["role"]),
        ("Is this at every branch?", []),
        ("Your name is Ayesha, right.", []),
    ],
)
def test_asked_keys_reads_only_question_sentences(reply, keys):
    assert mb.asked_keys(reply) == keys


# --- the linter: never ask twice (R-MEM-02) ----------------------------------------------------


def lint(reply, **ctx):
    base = {"history": [{"role": "ai", "text": "Hi, I'm pi, an AI."}], "reply_language": "en"}
    return {v.rule for v in c.lint(reply, {**base, **ctx})}


def test_a_fact_known_only_from_the_memory_block_is_not_asked_again():
    block = {"location": "Lahore", "team_size": "3 branches"}
    assert "R-MEM-02" in lint("Thanks. Which city are you based in?", what_i_know=block)
    assert "R-MEM-02" in lint("And how many staff do you have?", what_i_know=block)
    assert "R-MEM-02" not in lint("Thanks. Which city are you based in?")


def test_a_question_asked_and_left_unanswered_is_not_pressed_again():
    block = {"name": "Ata", "already_asked": ["location"]}
    assert "R-MEM-02" in lint("Which city are you based in?", what_i_know=block)
    assert "R-MEM-02" not in lint("What is happening with stock?", what_i_know=block)


def test_memory_check_ignores_other_questions_and_statements():
    block = {"location": "Lahore", "role": "owner"}
    assert "R-MEM-02" not in lint("Is it the Lahore branch that runs short?", what_i_know=block)
    assert "R-MEM-02" not in lint("You said you are based in Lahore.", what_i_know=block)


# --- what do you remember about me (R-PRIV-06) -------------------------------------------------


def test_the_memory_answer_lists_what_is_known_and_offers_deletion():
    text = mb.memory_reply({"name": "Ayesha", "location": "Lahore"}, "en", "fixed")
    assert "Ayesha" in text and "Lahore" in text and "delete" in text
    assert "aap ka naam: Ayesha" in mb.memory_reply({"name": "Ayesha"}, "roman_ur", "fixed")


def test_without_facts_the_fixed_line_is_used():
    assert mb.memory_reply({}, "en", "I keep the problems you told me.") == (
        "I keep the problems you told me."
    )
    assert mb.memory_reply({"last_time": "stock", "already_asked": ["name"]}, "en", "fixed") == (
        "fixed"
    )


def test_the_brain_gate_answers_the_memory_question_from_the_block():
    context = {
        "pi_mode": "brain",
        "latest_customer_message": "what do you remember about me?",
        "reply_language": "en",
        "history": [{"role": "ai", "text": "Hi, I'm pi, an AI."}],
        "what_i_know": {"name": "Ayesha", "business_name": "Noor Bakery"},
    }
    turn = sc.brain_safety(context)
    assert turn is not None and "Noor Bakery" in turn.reply and "delete" in turn.reply


# --- the prompt and the continuity around it ---------------------------------------------------


def test_the_prompt_only_carries_the_memory_rules_when_there_is_a_block():
    with_block = sc.system_for({"pi_mode": "brain", "what_i_know": {"name": "Ata"}})
    without = sc.system_for({"pi_mode": "brain"})
    assert mb.SYSTEM_LINE in with_block and mb.SYSTEM_LINE not in without
    assert len(with_block) - len(without) == len(mb.SYSTEM_LINE)
    assert len(mb.SYSTEM_LINE) < 600  # the whole added system text


def test_days_away_counts_the_earlier_conversation_when_this_one_is_new():
    now = datetime(2026, 10, 24, tzinfo=UTC)
    message = SimpleNamespace(id=1, created_at=now)
    assert sc.days_away(message, [], now - timedelta(days=9)) == 9
    assert sc.days_away(message, [], None) == 0
    mine = SimpleNamespace(id=2, sender_type="customer", created_at=now - timedelta(days=2))
    assert sc.days_away(message, [mine], now - timedelta(days=9)) == 2


def test_a_returning_person_in_a_new_conversation_is_welcomed_back():
    context = {
        "pi_mode": "brain",
        "history": [],
        "returning_customer": True,
        "noted_problems": [{"group": "stock_inventory"}],
        "days_away": 6,
        "reply_language": "en",
    }
    assert sc.welcome_back(context) is not None
    assert sc.welcome_back({**context, "returning_customer": False}) is None


def reply_language(body, remembered=None, rows=()):
    message = SimpleNamespace(body=body, message_type="text")
    return sc.reply_language(SimpleNamespace(language=None), message, list(rows), remembered)


def test_a_remembered_language_answers_a_bare_ok_in_a_new_chat():
    assert reply_language("ok")["reply_language"] == "en"
    assert reply_language("ok", "roman_ur")["reply_language"] == "roman_ur"
    # what they write now still wins over the memory
    assert reply_language("please send the list of branches", "roman_ur")["reply_language"] == "en"


class _BrokenSession:
    """A session whose savepoint works but whose statements fail (a missing table, a constraint)."""

    def begin_nested(self):
        class _Ctx:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, *exc):
                return False  # let the error through, as a real savepoint does

        return _Ctx()

    async def scalars(self, *a, **k):
        raise RuntimeError("relation does not exist")

    async def execute(self, *a, **k):
        raise RuntimeError("constraint")


async def test_a_memory_failure_never_fails_the_turn() -> None:
    """The memory reads and writes run in a savepoint and swallow errors: pi just knows nothing
    durable this turn, and the reply's transaction stays healthy."""
    from types import SimpleNamespace
    from uuid import uuid4

    from app.modules.pi import memory_block

    conversation = SimpleNamespace(id=uuid4(), customer_id=uuid4(), service_brief={})
    scope = SimpleNamespace(tenant_id=uuid4(), environment_id=uuid4())
    changed = await memory_block.refresh_safely(
        _BrokenSession(),  # type: ignore[arg-type]
        scope,  # type: ignore[arg-type]
        conversation,  # type: ignore[arg-type]
        profile={"business_type": "pharmacy"},
        language="en",
        voice_note=False,
        message_id=None,
    )
    assert changed == []
    known = await memory_block.load_safely(
        _BrokenSession(),  # type: ignore[arg-type]
        scope,  # type: ignore[arg-type]
        conversation,  # type: ignore[arg-type]
        None,
    )
    assert known.facts == {} and known.prefs == {}
