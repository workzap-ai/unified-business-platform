"""The platform specification replaced parts of Brain v3 (page 5, "Which rule wins"): the handbook
the model is given every turn must carry the governing text, never the superseded one."""

import hashlib
import json

import pytest

from app.modules.pi import flow, learning_audit, spec_handbook

STATES = (flow.State.S1_LISTENING, flow.State.S3_NOTED, flow.State.S5_READINESS)
OLD_LINES = (
    "MUST NOT suggest a solution",
    "once the problems are noted",
    "MUST NOT mention a solution document or quote until",
)


@pytest.mark.parametrize("state", STATES)
def test_the_guidance_never_carries_a_superseded_listen_only_rule(state):
    text = spec_handbook.guidance(state.name)
    for line in OLD_LINES:
        assert line not in text, (state.name, line)


@pytest.mark.parametrize("state", STATES)
def test_the_guidance_carries_the_governing_answer_first_rules(state):
    text = spec_handbook.guidance(state.name)
    for rule in ("R-ANS-01", "R-ANS-02", "R-ANS-03", "R-SOL-01", "R-SOL-04", "R-SOL-07"):
        assert rule in text, (state.name, rule)
    assert "R-SELL-03" in text and "R-SELL-05" in text  # these two stand
    assert "first sentence" in text  # R-ANS-01 and the 1.2 banner


def test_the_owners_two_decisions_keep_two_book_2_rules_out():
    """The owner chose the progress rule only (no unprompted offer after four stuck turns) and a
    scope question on a plain yes: so R-SOL-10 and R-OFFER-07 are not taught to the model."""
    book = spec_handbook.sections()
    text = book["1.2"]["text"]
    assert "R-SOL-10" not in text and "R-OFFER-07" not in text
    data = json.loads(spec_handbook.SUPERSESSION.read_text(encoding="utf-8"))
    assert set(data["excluded"]) == {"R-SOL-10", "R-OFFER-07"}


def test_every_patch_still_applies_to_the_handbook_it_patches():
    """A stale patch (a fragment the handbook no longer has) would silently stop working."""
    raw = {i["id"]: i for i in json.loads(spec_handbook.PATH.read_text(encoding="utf-8"))}
    data = json.loads(spec_handbook.SUPERSESSION.read_text(encoding="utf-8"))
    for patch in data["patch"]:
        assert patch["old"] in raw[patch["id"]]["text"], patch["id"]
        assert patch["new"] in spec_handbook.sections()[patch["id"]]["text"]
    for item in data["replace"]:
        assert item["id"] in raw  # a replacement of a section that exists


def test_the_prompt_version_changes_when_the_supersession_changes():
    version = learning_audit.prompt_version()
    handbook_only = hashlib.sha256(spec_handbook.PATH.read_bytes()).hexdigest()[:12]
    assert version and version != handbook_only


def test_g4_stays_until_the_owner_decides():
    """Spec G4 against Book 2 4.2 is an open decision, not silently dropped."""
    assert "G4" in spec_handbook.sections()
