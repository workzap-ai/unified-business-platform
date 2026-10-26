"""R-ASK-07 (Book 2 10.4, Book 4 5.3): a question the person answered, even with "no" or "pata
nahi", is closed for good, across sessions and languages (the Tipu Sultan repeat, cause 8)."""

from app.modules.pi import slots


def test_the_question_of_a_reply_is_its_last_question():
    reply = "Noted. Ye kis branch mein zyada hota hai? Aur kab se?"
    assert slots.question_of(reply) == "Aur kab se?"
    assert slots.question_of("Noted, thanks.") == ""


def test_an_answer_closes_the_question_asked_before_it():
    previous = {
        "last_question": {"slot": "branch.taste_changes", "q": "Ye kis branch mein zyada hota hai?"}
    }
    closed, opened = slots.advance(previous, "Tipu sultan wali", "Noted. Aur kab se?", "since.when")
    assert closed == [{"slot": "branch.taste_changes", "q": "Ye kis branch mein zyada hota hai?"}]
    assert opened == {"slot": "since.when", "q": "Aur kab se?"}


def test_even_no_or_dont_know_closes_it_but_a_solution_ask_does_not():
    previous = {
        "last_question": {"slot": "ads.other", "q": "Kya aap koi aur marketing karte hain?"}
    }
    for said in ("no", "pata nahi", "\U0001f44d", "hmm"):
        closed, _ = slots.advance(previous, said, "Noted.", "")
        assert [c["slot"] for c in closed] == ["ads.other"], said
    closed, _ = slots.advance(previous, "Solution dain", "Noted.", "")
    assert closed == []  # asking for ideas is not an answer: the question stays open


def test_a_slot_is_closed_once_not_twice():
    previous = {
        "closed_slots": [{"slot": "shops.count", "q": "Kitni dukaanein hain aap ki?"}],
        "last_question": {"slot": "shops.count", "q": "How many shops do you have?"},
    }
    closed, _ = slots.advance(previous, "four", "Noted.", "")
    assert len(closed) == 1


def test_asking_a_closed_slot_again_is_found_by_its_name_across_languages():
    closed = [{"slot": "branch.taste_changes", "q": "Ye kis branch mein zyada hota hai?"}]
    english = "Where does the taste change most, the same branch or different ones?"
    assert slots.asked_again("branch.taste_changes", english, closed)
    assert slots.asked_again("since.when", english, closed) is None


def test_asking_the_same_question_in_other_words_is_found_without_a_slot_name():
    closed = [{"slot": "", "q": "Which shop loses the most customers on weekends?"}]
    assert slots.asked_again("", "Which shop loses most customers on weekends, then?", closed)
    assert slots.asked_again("", "How many staff work at that shop?", closed) is None
    assert slots.asked_again("", "Noted, thanks.", closed) is None


def test_only_the_last_twenty_four_slots_are_kept():
    previous = {
        "closed_slots": [
            {"slot": f"s.{i}", "q": f"question number {i} alpha beta"} for i in range(30)
        ],
        "last_question": {"slot": "s.new", "q": "completely different question about delivery"},
    }
    closed, _ = slots.advance(previous, "yes", "Noted.", "")
    assert len(closed) == slots.KEEP and closed[-1]["slot"] == "s.new"
