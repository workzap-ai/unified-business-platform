"""The expert advisor voice (live chat, 2026-10-27): no noted opener, no "the team will see this",
and "kuch karo" is a request for a fix."""

import pytest

from app.modules.pi import constitution, expert_advisor, solution_ask

CTX = {
    "pi_mode": "brain",
    "expert_on": True,
    "flow": {"state": "S3_NOTED"},
    "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
}


def rules(reply: str, **over: object) -> set[str]:
    return {v.rule for v in constitution.lint(reply, {**CTX, **over})}


def test_the_live_noted_opener_and_the_team_claim_are_caught() -> None:
    reply = (
        "Note kar liya: har mahine 80 se zyada parents ki fee late hoti hai. Ye team tak bhi "
        "pohanch jayega. Parents fee kaise jama karwate hain?"
    )
    found = rules(reply)
    assert "R-ECHO-05" in found and "R-DISC-06" in found


def test_a_question_about_the_reason_is_clean() -> None:
    assert not rules(
        "Jab accounts wala late parent se baat karta hai, to wo kya wajah batate hain?"
    ) & {
        "R-ECHO-05",
        "R-DISC-06",
    }


def test_the_noted_ban_is_everywhere_the_team_line_is_expert_only() -> None:
    # spec v1.4, 17.6: no "noted" announcement in any brain workspace
    assert "R-ECHO-05" in rules("Note kar liya: fee late hoti hai. Kya wajah hai?", expert_on=False)
    assert "R-DISC-06" not in rules("Ye team tak pohanch jayega. Kya wajah hai?", expert_on=False)


def test_the_voice_rule_is_in_the_expert_prompt_and_not_without_it() -> None:
    from app.modules.pi.service_conversation import system_for

    assert expert_advisor.VOICE_RULE in system_for({"pi_mode": "brain", "expert_on": True})
    assert expert_advisor.VOICE_RULE not in system_for({"pi_mode": "brain"})


@pytest.mark.parametrize(
    "said",
    ["kuch karo", "kuch kro", "kuch to karo", "kuch kijiye", "kuch kar do", "Kuch karo please"],
)
def test_do_something_is_an_ask_for_a_fix(said: str) -> None:
    assert solution_ask.asked_for_ideas(said)


@pytest.mark.parametrize(
    "said", ["kuch nahi karna", "mujhe kuch nahi kehna", "kuch masla hai", "hello"]
)
def test_a_refusal_or_a_plain_sentence_is_not(said: str) -> None:
    assert not solution_ask.asked_for_ideas(said)
