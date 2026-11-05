"""Speaker labels are roles or "Speaker N": a person's name from a transcript is never kept."""

from app.modules.pi_meetings.routes import _lines


def test_a_name_becomes_a_numbered_speaker_and_roles_are_kept():
    out = _lines("Ahmed Khan: hello\nSara: hi\nCustomer: ok\nAhmed Khan: again\nSpeaker 2: x")
    labels = [label for label, _ in out]
    assert labels[0] == "Speaker 1" and labels[3] == "Speaker 1"  # the same person, the same label
    assert labels[1] == "Speaker 2" and labels[2] == "Customer"
    assert labels[4] != labels[1]  # an explicit "Speaker 2" never merges with a generated one
    assert not any("Ahmed" in label or "Sara" in label for label in labels)
