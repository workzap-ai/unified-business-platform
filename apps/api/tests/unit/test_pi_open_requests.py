"""R-ANS-03 (Book 2 10.4): a request left unanswered for one reply is dealt with before anything
else. Timeline and human requests are tracked here (a solution request has its own carry-over, the
price answer is a fixed line)."""

from app.modules.pi import open_requests as oq


def test_the_tracked_requests_in_a_message():
    assert oq.kinds("kitne din lagenge?") == ["timeline"]
    assert oq.kinds("How long will it take?") == ["timeline"]
    assert oq.kinds("mujhe kisi insaan se baat karni hai") == ["human"]
    assert oq.kinds("can I talk to a person") == ["human"]
    assert oq.kinds("stock khatam ho jata hai") == []


def test_a_request_the_reply_ignores_stays_open_and_one_it_answers_does_not():
    left = oq.update(None, "kitne din lagenge?", "Noted. Which shop is worst?")
    assert left == [{"kind": "timeline", "turns": 1}]
    answered = oq.update(
        None, "kitne din lagenge?", "The quote says how long it takes. Which shop?"
    )
    assert answered == []
    human = oq.update(None, "I want to talk to a person", "Noted.", request_human=True)
    assert human == []


def test_the_next_reply_is_checked_against_what_was_left_open():
    open_ = [{"kind": "timeline", "turns": 1}]
    assert oq.unanswered(open_, "Noted. What else?") == ["timeline"]
    assert oq.unanswered(open_, "The quote will say how long it takes.") == []
    assert oq.unanswered([{"kind": "human", "turns": 1}], "Noted.") == ["human"]
    assert oq.unanswered([{"kind": "human", "turns": 1}], "Noted.", request_human=True) == []
    assert oq.unanswered(None, "anything") == []


def test_a_request_that_stays_unanswered_is_dropped_after_three_replies():
    state = oq.update(None, "kitne din lagenge?", "Noted.")
    for _ in range(oq.MAX_OPEN_TURNS):
        state = oq.update(state, "ok", "Noted.")
    assert state == []
