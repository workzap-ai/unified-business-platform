"""The golden replies of docs/pi-saas/pi-golden-replies.md pass the reply linter in brain mode.

They are the target voice (owner-approved, 2026-10-26): if the linter rejects one, either
the linter is too strict for pi's real voice or the golden reply broke a rule. Fix whichever."""

import pytest

from app.modules.pi import constitution
from app.modules.pi.golden_replies import GOLDEN

HISTORY = [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}]


@pytest.mark.parametrize(("state", "language", "said", "reply"), GOLDEN)
def test_a_golden_reply_breaks_no_rule(state, language, said, reply):
    context = {
        "pi_mode": "brain",
        "flow": {"state": state},
        "reply_language": language,
        "history": HISTORY,
        "solution_asked": "ideas" in reply,
    }
    found = [v.rule for v in constitution.lint(reply, context)]
    assert not found, found


def test_the_listening_golden_replies_pass_the_seed_gate():
    from app.modules.pi import golden_replies, learning_seed

    listening = golden_replies.listening()
    assert listening  # the ideas and the offer reply are not seeded: they have their own gate
    assert all("•" not in reply for _, _, _, reply in listening)
    refused = [said for _, _, said, reply in listening if not learning_seed.admit(said, reply)[0]]
    assert refused == [], refused
