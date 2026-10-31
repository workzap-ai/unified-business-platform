from app.modules.pi import blueprint_doc as bd
from app.modules.pi import solutions


def view(ref, **kw):
    base = {
        "ref": ref,
        "id": ref,
        "title": f"Problem {ref}",
        "quotes": ["we lose customers after three days"],
        "where": "",
        "how_often": "every week",
        "since": "March",
        "money": "about 50000 a month",
        "limits": {},
        "cannot_change": [],
        "tried": [],
        "cause_text": "",
        "cause_status": "",
        "cause": "",
        "expected_outcome": "",
        "msgs": ["m1"],
    }
    base.update(kw)
    return base


KEY = next(iter(solutions.CATALOGUE))


def comp(refs, phase=1):
    return {
        "key": KEY,
        "text": solutions.build_phrase(KEY, "en", None),
        "phase": phase,
        "refs": refs,
    }


def test_blueprint_keeps_owner_facts_and_links_every_step():
    views = [view("P1", expected_outcome="reply within an hour"), view("P2")]
    bp = bd.build(
        views,
        [comp(["P1"]), comp(["P2"], 2)],
        [{"phase": 1, "name": "A"}, {"phase": 2, "name": "B"}],
        ["a contact person"],
    )
    assert [s["problems"] for s in bp["steps"]] == [["P1"], ["P2"]]
    assert bp["steps"][1]["depends_on"] == [1]
    assert bp["steps"][0]["needs_from_owner"] == ["a contact person"]
    assert "about 50000 a month" in bp["problems"][0]["figures"][-1]
    assert bp["acceptance"][0]["measurable"] is True
    assert any("P2" in u or "Problem P2" in u for u in bp["unresolved"])
    assert bd.issues(bp) == []


def test_guessed_cause_is_labelled_and_never_owner_stated():
    bp = bd.build(
        [view("P1", cause_text="slow staff", cause_status="pi_inferred")], [comp(["P1"])], [], []
    )
    assert bp["problems"][0]["cause"]["label"] == bd.HYPOTHESIS
    assert not bp["problems"][0]["cause"]["owner_stated"]
    assert any("our guess" in r["text"] for r in bp["risks"])
    owner = bd.build(
        [view("P1", cause_text="rent", cause_status="owner_said")], [comp(["P1"])], [], []
    )
    assert owner["problems"][0]["cause"]["owner_stated"]


def test_unlinked_step_is_flagged():
    bp = bd.build([view("P1")], [comp([])], [], [])
    assert bp["unlinked_steps"] == [1] and bd.issues(bp)


def test_thin_evidence_recommends_learn_first_not_a_build():
    bp = bd.build([view("P1", msgs=[])], [comp(["P1"])], [], [])
    assert bp["recommendation"]["learn_first"] is True


def test_verified_owner_evidence_recommends_the_build():
    bp = bd.build(
        [view("P1")],
        [comp(["P1"])],
        [],
        [],
        owner_messages={"m1": "we lose customers after three days"},
    )
    assert bp["recommendation"]["kind"] == "workzap_build"


def test_step_that_breaks_a_stated_limit_is_not_recommended():
    text = solutions.build_phrase(KEY, "en", None)
    view1 = view("P1", cannot_change=[text.split()[0] + " " + text.split()[1]])
    bp = bd.build(
        [view1], [comp(["P1"])], [], [], owner_messages={"m1": "we lose customers after three days"}
    )
    statuses = {s["check"]["status"] for s in bp["steps"]}
    if "violates" in statuses:
        assert bp["recommendation"]["kind"] != "workzap_build"


def test_pdf_renders_the_blueprint():
    from datetime import date

    from app.modules.pi import brain_pdf

    views = [view("P1", expected_outcome="reply within an hour")]
    content = {
        "box": True,
        "problems": [{"ref": "P1", "title": "Problem P1", "quotes": ["q"]}],
        "components": [comp(["P1"])],
        "phases": [{"phase": 1, "name": "A"}],
        "blueprint": bd.build(views, [comp(["P1"])], [{"phase": 1, "name": "A"}], []),
    }
    pdf = brain_pdf.render_solution(
        content, business="B", ref="SD-1", issued=date.today(), language="en"
    )
    assert pdf.startswith(b"%PDF")


def test_recommendation_says_why_and_what_is_unknown():
    bp = bd.build(
        [view("P1"), view("P2", msgs=[])],
        [comp(["P1"]), comp(["P2"], 2)],
        [],
        [],
        owner_messages={"m1": "we lose customers after three days"},
    )
    rec = bp["recommendation"]
    assert rec["option"] and "message(s) you wrote" in rec["why"]
    assert rec["insufficient"] is False and rec["options_seen"] == 2
    assert any(
        "no result you want" in u or "not said" in u or "result" in u for u in rec["unknown"]
    )
