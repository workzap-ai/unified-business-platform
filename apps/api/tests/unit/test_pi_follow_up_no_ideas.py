"""Platform spec Book 4 5.4, cause 6 of Live Audit 2: a follow-up after silence never carries new
solutions. The earlier request ("Solution dain") is still the latest inbound message, so the
detector handed over ideas again 18 hours later, for the wrong problem."""

from app.modules.pi import check_in


def test_a_quiet_follow_up_context_loses_every_solution_field():
    context = {
        "latest_customer_message": "Solution dain",
        "solution_asked": True,
        "solution_ideas": ["First, ...", "Second, ..."],
        "solution_build": "Workzap could ...",
        "solution_never_say": ["x"],
        "noted_problems": [{"ref": "a"}],
        "closed_slots": [{"slot": "branch.where", "q": "Which branch?"}],
        "check_in_now": {"missed": False},
    }
    out = check_in.without_solutions(context)
    assert not [k for k in out if k.startswith("solution_")]
    assert out["noted_problems"] and out["closed_slots"] and out["check_in_now"]  # the rest stays


def test_a_follow_up_that_still_carries_ideas_is_not_sent():
    ideas = "Pichli baat wahin se.\nPehle, ek banda roz check kare.\nDoosra, wait time likhein."
    assert check_in.carries_ideas(ideas)
    assert check_in.carries_ideas("Here are two things.\nFirst, count the slips.\nSecond, ...")
    assert not check_in.carries_ideas(
        "Pichli baat wahin se jaari rakhein? Aap ne taste batayi thi."
    )
    assert not check_in.carries_ideas("Shall I get a solution document and a quote made for you?")
