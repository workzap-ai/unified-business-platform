"""Platform spec v1.4, 17.2 (A41/A42): strain first, direct questions, and one common word is not
coverage."""

from app.modules.pi import turn_coverage as tc

STRAIN = (
    "main bohat tang aa gaya hoon, sales team bahane banati hai aur customers ko call nahi karti"
)
TURN = [STRAIN, "stock kitna hai godown mein", "invoice kab bhejna hai"]


def test_one_common_word_no_longer_counts_as_covering_the_biggest_topic() -> None:
    # "team" is the only shared word: before, that was enough
    reply = "Aap ki team kitni badi hai? Godown ka stock aap kis register mein likhte hain?"
    assert tc.skipped_topic(reply, TURN) is not None


def test_two_shared_words_cover_the_topic() -> None:
    reply = "Sales team ka bahane banana tang karta hai. Godown ka stock kitna hai batayen?"
    assert tc.skipped_topic(reply, TURN) is None


def test_strain_must_be_acknowledged_in_the_first_sentence() -> None:
    flat = "Godown mein stock kitna hai? Main bata deta hoon."
    assert tc.skipped_strain(flat, TURN) == STRAIN
    kind = "Ye sun kar afsos hua, sales team ka yun bahane banana mushkil hai. Stock 40 hai."
    assert tc.skipped_strain(kind, TURN) is None


def test_the_owners_own_strain_word_counts_as_an_acknowledgement() -> None:
    assert tc.skipped_strain("Tang aa jana samajh aata hai. Stock kitna hai?", TURN) is None


def test_strain_in_a_middle_or_last_message_is_checked_too() -> None:
    turn = ["stock kitna hai", "sab kuch theek hai", "aaj bohat thak gaya hoon yaar"]
    assert tc.skipped_strain("Stock 40 hai.", turn) == turn[2]
    assert tc.skipped_strain("Thak jana natural hai. Stock 40 hai.", turn) is None


def test_a_direct_question_that_the_reply_ignores_is_flagged() -> None:
    turn = ["hamari dukan Lahore mein hai", "invoice kab bhejna hai customer ko?"]
    assert tc.skipped_question("Aap ka business kitne saal se chal raha hai?", turn) == turn[1]
    assert tc.skipped_question("Invoice customer ko delivery ke baad bhejein.", turn) is None


def test_a_single_message_and_unspaced_scripts_are_left_alone() -> None:
    assert tc.skipped_question("anything", ["kya aap kar sakte hain?"]) is None
    assert tc.skipped_strain("anything", [STRAIN]) is None
    assert tc.skipped_question("はい", ["私の店は?", "在庫が足りません どうして?"]) is None


def test_coverage_problem_names_the_first_failure_and_passes_a_good_reply() -> None:
    bad = tc.coverage_problem("Godown mein kya hai?", TURN)
    assert bad is not None and "strain" in bad
    good = (
        "Sales team ke bahane tang karte hain, samajh aata hai. Godown ka stock kitna hai, "
        "aur invoice kab bhejna hai, dono batata hoon."
    )
    assert tc.coverage_problem(good, TURN) is None


def test_the_rewrite_for_a_skipped_question_quotes_it() -> None:
    reason = tc.coverage_problem(
        "Sales team ka masla sunna chahta hoon, tang hona natural hai.",
        ["hello there my friend", "invoice kab bhejna hai customer ko?"],
    )
    assert reason is not None and "invoice kab" in reason
