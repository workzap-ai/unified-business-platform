"""Platform spec v1.4, 17.2 (turnCoverage): a reply that skips the biggest message of a burst."""

from app.modules.pi import turn_coverage as tc

SALES = (
    "Meri sales team disappear ho jati hai aur bahane banati hai, main tang aa gaya hoon "
    "in sab se, customers ke call tak nahi uthate"
)


def test_a_reply_that_drops_the_heartfelt_first_message_is_flagged() -> None:
    turn = [SALES, "stock kitna hai", "godown mein kya bacha"]
    reply = "Godown ka stock aap kis register mein likhte hain?"
    assert tc.skipped_topic(reply, turn) == SALES


def test_a_reply_that_touches_it_passes() -> None:
    turn = [SALES, "stock kitna hai", "godown mein kya bacha"]
    reply = "Sales team ka disappear hona mushkil hai. Aap unke calls kaise dekhte hain?"
    assert tc.skipped_topic(reply, turn) is None


def test_the_longest_message_is_chosen_and_strain_counts_for_more_words() -> None:
    long_plain = "the delivery van keeps arriving late to the north side of the city every week"
    assert tc.biggest(["i am exhausted and fed up", long_plain, "ok"]) == 0
    assert tc.biggest([long_plain, "ok"]) == 0
    assert tc.biggest(["one two", "one two three four"]) == 1


def test_one_message_a_short_aside_or_the_newest_are_never_flagged() -> None:
    assert tc.skipped_topic("Which shop is it?", [SALES]) is None
    assert tc.skipped_topic("Which shop is it?", ["hello there", "stock kitna hai bhai"]) is None
    assert tc.skipped_topic("anything at all", ["hi", SALES]) is None  # the newest is the biggest
    assert tc.skipped_topic("", ["a b c d e f g h", "hi"]) is None


def test_unspaced_scripts_are_left_alone() -> None:
    assert (
        tc.skipped_topic("はい", ["私の店は毎週在庫が足りなくなって本当に困っています", "hi"])
        is None
    )


def test_the_rewrite_reason_quotes_the_topic_and_the_turn_note_names_the_queue() -> None:
    assert "Sales team" not in tc.rewrite_reason("x" * 400)  # a long topic is cut
    assert SALES[:40] in tc.rewrite_reason(SALES)
    assert "while pi was down" in tc.turn_note(True)
    assert "while pi was down" not in tc.turn_note(False)
