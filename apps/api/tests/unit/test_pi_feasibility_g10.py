"""Platform spec v1.4, 17.4 G10 (TS5, A46): an idea the owner's stated means cannot carry."""

from app.modules.pi import feasibility, idea_filter

OWNER = "Hamare paas do technician hain aur dono raat ko jobs par hote hain, calls miss hoti hain"
ON_CALL = "Keep a named on-call person always available for every night call."


def test_the_spec_case_two_technicians_and_a_named_on_call_person() -> None:
    assert feasibility.resources_of(OWNER).people == 2
    assert feasibility.check(ON_CALL, OWNER) == "G10"
    assert "always available" in (feasibility.infeasible(ON_CALL, OWNER) or "")


def test_unstated_size_is_not_judged() -> None:
    assert feasibility.check(ON_CALL, "calls miss hoti hain raat ko") is None
    assert feasibility.check(ON_CALL, "we have twelve technicians on the roster") is None


def test_a_solo_owner_cannot_staff_a_dedicated_team() -> None:
    owner = "I work alone, so enquiries pile up"
    assert feasibility.resources_of(owner).people == 1
    assert feasibility.check("Set up a dedicated team for follow-ups.", owner) == "G10"
    assert feasibility.check("Send a message back to every enquiry within the hour.", owner) is None


def test_every_branch_with_one_shop() -> None:
    owner = "Mera ek shop hai aur stock ka hisab nahi milta"
    assert feasibility.check("Count stock at every branch each Friday.", owner) == "G10"
    assert feasibility.check("Count stock on the shelves each Friday.", owner) is None


def test_an_idea_that_fits_two_people_passes() -> None:
    idea = "Whoever finishes a job first calls back the missed callers first."
    assert feasibility.check(idea, OWNER) is None


def test_the_filter_withholds_it_only_when_resources_are_set() -> None:
    assert "G10" not in idea_filter.failures(ON_CALL, OWNER)
    ctx = idea_filter.with_resources(None, OWNER)
    assert ctx is not None and "G10" in idea_filter.failures(ON_CALL, OWNER, ctx)
    assert idea_filter.with_resources(None, "  ") is None


def test_the_reply_guard_names_the_sentence_and_ignores_questions() -> None:
    reply = "Missed calls cost you work. Keep a named on-call person always available. Sound ok?"
    hint = feasibility.reply_problem(reply, OWNER)
    assert hint is not None and hint.startswith("G10")
    asking = "Do you keep someone on call at night?"
    assert feasibility.reply_problem(asking, OWNER) is None
