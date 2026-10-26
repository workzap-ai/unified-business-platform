"""Platform spec Part A.5 and Book 4 5.1: brain mode has its own prompt, not the account manager's
playbook with a line that says "this replaces the rules above". Every other workspace keeps SYSTEM
exactly as it was."""

import pytest

from app.modules.pi import brain_prompt
from app.modules.pi import service_conversation as sc

REMOVED = (
    "the company's real team reads this chat",
    "best account manager",
    "Qualify the lead",
    "ask in one short friendly question\nfor their name",
    "Ideas: when the customer asks",
    "Ask at most two short, related questions per reply",
    'Projects still "collecting"',
    "Proposals:\n- When the customer asks where things stand",
    'action="payment"',
    "A project document they just sent",
    "Shall I send this to the team",
    "(name, what it does)",
)
KEPT = (
    "wants_person: true ONLY",
    "NEVER quote, estimate, suggest, repeat or promise a service price",
    "customer_profile from the customer's own words only",
    "Meetings: when the customer asks for a meeting",
    "shared_documents:",
    "shared_links:",
    "Reply strictly in the",
    "Language (strict)",
    "Think before you write",
    "Understanding (fill",
    "UNTRUSTED DATA",
)


def flat(text: str) -> str:
    return " ".join(text.split())


def test_every_other_workspace_still_gets_exactly_the_same_prompt():
    assert sc.system_for({}) is sc.SYSTEM
    assert sc.system_for({"pi_mode": "standard"}) is sc.SYSTEM


@pytest.mark.parametrize("phrase", REMOVED)
def test_the_brain_prompt_has_none_of_the_account_manager_playbook(phrase):
    assert flat(phrase) in flat(sc.SYSTEM), "the phrase must exist in SYSTEM or the test is stale"
    assert flat(phrase).lower() not in flat(sc.BRAIN_SYSTEM).lower()


@pytest.mark.parametrize("phrase", KEPT)
def test_the_brain_prompt_keeps_the_shared_rules_it_still_needs(phrase):
    assert flat(phrase) in flat(sc.BRAIN_SYSTEM)


def test_the_brain_prompt_is_the_brain_blocks_on_the_shorter_system():
    prompt = sc.system_for({"pi_mode": "brain"})
    assert prompt.startswith(sc.BRAIN_SYSTEM)
    assert sc.BRAIN_PROBLEMS in prompt and sc.BRAIN_VOICE in prompt
    assert len(sc.BRAIN_SYSTEM) < 0.75 * len(sc.SYSTEM)


def test_a_cut_that_no_longer_matches_fails_loudly_instead_of_silently():
    with pytest.raises(ValueError):
        brain_prompt.cut("a prompt that was edited", brain_prompt.CUTS)
    with pytest.raises(ValueError):
        brain_prompt.cut("start here, no end", (("start here", "missing end", ""),))
    assert brain_prompt.cut("aXb tail", (("X", "b", "-"),)) == "a-b tail"
    assert brain_prompt.cut("keep|drop all", (("|", None, ""),)) == "keep"
