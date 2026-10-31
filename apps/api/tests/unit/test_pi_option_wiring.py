from app.modules.pi import option_wiring as ow
from app.modules.pi.requirements_types import Constraints, Limit, ProblemRequirements, Requirements


def reqs(**kw):
    c = Constraints(**kw)
    return Requirements(problems=(ProblemRequirements(constraints=c),))


def test_roundtrip_context():
    r = reqs(cannot_change=(Limit("hire more staff"),))
    again = ow.requirements_from(ow.requirements_context(r))
    assert [x.text for x in again.cannot_change] == ["hire more staff"]
    assert ow.requirements_context(Requirements()) == {}


def test_unreadable_requirements_survive_the_roundtrip():
    packed = ow.requirements_context(Requirements(columns_available=False))
    assert ow.requirements_from(packed).columns_available is False
