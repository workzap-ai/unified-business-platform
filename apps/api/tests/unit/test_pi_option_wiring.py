from app.modules.pi import option_wiring as ow
from app.modules.pi.requirements_types import Constraints, Limit, ProblemRequirements, Requirements


def reqs(**kw):
    c = Constraints(**kw)
    return Requirements(problems=(ProblemRequirements(constraints=c),))


def test_nothing_stated_changes_nothing():
    w = ow.gate_ideas(["Send a reminder message."], Requirements())
    assert w.shown == ["Send a reminder message."] and not w.changed


def test_roundtrip_context():
    r = reqs(cannot_change=(Limit("hire more staff"),))
    again = ow.requirements_from(ow.requirements_context(r))
    assert [x.text for x in again.cannot_change] == ["hire more staff"]
    assert ow.requirements_context(Requirements()) == {}


def test_violating_idea_dropped_with_reason_and_question_when_none_left():
    r = reqs(cannot_change=(Limit("hire more staff"),))
    w = ow.gate_ideas(["Hire more staff for the evening."], r)
    assert not w.shown and w.rejected and "cannot change" in w.notice
    assert w.question.endswith("?") and w.question.count("?") == 1


def test_unreadable_requirements_are_unknown_not_confirmed():
    w = ow.gate_ideas(["Send a reminder message."], Requirements(columns_available=False))
    assert w.shown and ow.NOT_CHECKED in w.shown[0]
    assert (
        ow.requirements_from(
            ow.requirements_context(Requirements(columns_available=False))
        ).columns_available
        is False
    )
