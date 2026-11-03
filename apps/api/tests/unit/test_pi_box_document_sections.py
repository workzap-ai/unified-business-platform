"""The Solution Box document as the spec's eight sections (Book 5, 5.2, 5.6, 5.7): clusters and
hypotheses, two ideas per problem, catalogue only, phases, order of work, assumptions, the quote by
phase and the "Naya:" list."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.pi import box_doc, brain_docs, brain_pdf, solutions
from app.modules.pi.brain_docs import BoxComponent, BoxDraft, Line, WontDo


@pytest.fixture(autouse=True)
def short_refs(monkeypatch):
    """The fixtures' ids are "id1", "id2": their short refs are P1, P2 (real ones hash UUIDs)."""
    monkeypatch.setattr(brain_docs.problems, "short_ref", lambda value: f"P{str(value)[-1]}")


def row(n, title, category="inventory", rank=None, **bits):
    return SimpleNamespace(
        id=f"id{n}",
        title=title,
        category=category,
        user_words=[f"{title} said"],
        scope={"where": bits.get("where", ["two shops"])},
        frequency={"text": bits.get("often", "weekly")},
        since={"text": bits.get("since", "")},
        impact={"types": ["lost_sales"], "money_text": bits.get("money", "")},
        person_believes_cause=bits.get("cause", ""),
        tags=[f"rank:{rank}"] if rank else [],
    )


ROWS = [
    row(1, "Stock runs out", rank=2, since="last year"),
    row(2, "Cashiers come late", "people_staff", rank=1, cause="no rota"),
    row(3, "Orders get lost", "sales_orders", money="two lakh a month"),
]
VIEWS = [box_doc.problem_view(r, f"P{r.id[-1]}") for r in ROWS]


def ideas(ref, a="Walk the shelves every Monday so you see gaps early.", b=None):
    b = b or "Ask each cashier to text you when they will be late, so you can cover the till."
    return [Line(text=a, refs=[ref]), Line(text=b, refs=[ref])]


def draft(**changes):
    base = dict(
        components=[
            BoxComponent(key="stock_alerts", phase=1, problems=["P1"]),
            BoxComponent(key="order_capture", phase=3, problems=["P3"]),
            BoxComponent(key="dashboards_reports", phase=3, problems=["P2"]),
        ],
        phases=[
            Line(text="Stop stock running out"),
            Line(text="Unused"),
            Line(text="See everything each morning"),
        ],
        hypotheses=[Line(text="The late supplier may be why stock runs out.", refs=["P1"])],
        ideas=[*ideas("P1"), *ideas("P2"), *ideas("P3")],
        assumptions=[Line(text="We assume each shop has a phone that can take messages.")],
        covers=["Your shops"],
        wont_do=[WontDo(text="It would not change how you order from suppliers.")],
        needs=["One contact person in each shop"],
    )
    return BoxDraft(**{**base, **changes})


def built(**changes):
    d = draft(**changes)
    plain, key_issues = brain_docs.box_to_solution(d, language="en", sector=None)
    content = brain_docs.solution_content(
        plain, ROWS_FOR_CONTENT, business="B", ref="SD-0001", language="en", local=False
    )
    return (
        d,
        key_issues,
        brain_docs.apply_box(
            content, d, views=VIEWS, links=[], language="en", local=False, sector=None
        ),
    )


ROWS_FOR_CONTENT = [
    SimpleNamespace(
        id=r.id,
        title=r.title,
        title_local="",
        user_words=r.user_words,
        scope=r.scope,
        frequency=r.frequency,
        since=r.since,
    )
    for r in ROWS
]


def test_every_catalogue_phrase_passes_the_document_rules():
    # section 4 is the catalogue's own wording, so it must be fit to go in front of a reviewer
    for key in solutions.CATALOGUE:
        for sector in (None, "7.I Health and care"):
            text, _ = box_doc.catalogue_text(key, "en", sector)
            plain = brain_docs.SolutionDraft(
                components=[brain_docs.Component(text=text, problems=["P1"])],
                wont_do=[WontDo(text="It would not change anything else.")],
            )
            issues = brain_docs.check_solution(plain, {"P1"})
            assert issues == [], (key, issues)


def test_a_key_outside_the_catalogue_is_refused():
    d = draft(components=[BoxComponent(key="invent_a_crm", phase=1, problems=["P1"])])
    plain, issues = brain_docs.box_to_solution(d, language="en", sector=None)
    assert plain.components == [] and "approved catalogue" in issues[0]


def test_the_eight_section_box_is_built_and_passes_its_own_checks():
    d, key_issues, content = built()
    assert key_issues == []
    assert content["box"] is True
    # 4: catalogue wording, phases closed up (1 and 3 become 1 and 2), named from the model's list
    assert [c["phase"] for c in content["components"]] == [1, 2, 2]
    assert [p["phase"] for p in content["phases"]] == [1, 2]
    assert content["phases"][0]["name"] == "Stop stock running out"
    assert content["phases"][1]["name"] == "See everything each morning"
    assert content["components"][0]["text"] == solutions.build_phrase("stock_alerts")
    # 2: clusters by category, the best ranked group first, hypotheses labelled by the PDF
    assert [c["problems"] for c in content["clusters"]] == [["P2"], ["P1"], ["P3"]]
    stock = next(c for c in content["clusters"] if "P1" in c["problems"])
    assert stock["hypotheses"] == ["The late supplier may be why stock runs out."]
    assert "Where: two shops" in stock["happening"][0]["line"]
    # 3: two ideas each
    assert [len(e["ideas"]) for e in content["ideas"]] == [2, 2, 2]
    # 5: the owner's ranking, P2 then P1, then the unranked one
    assert [o["ref"] for o in content["order"]] == ["P2", "P1", "P3"]
    # 7: model assumptions plus every detail the owner has not confirmed
    joined = " ".join(content["assumptions"])
    assert "We assume each shop has a phone" in joined
    assert "Cashiers come late: not yet confirmed with you: since when" in joined
    assert brain_docs.check_content(content) == []


def test_section_3_must_pass_the_value_line():
    # only one idea for P3, a how-to for P1, a figure for P2
    d = draft(
        ideas=[
            *ideas("P1", a="Open Excel and click Insert, then Pivot Table, step by step."),
            *ideas("P2", b="Do this and you will save 40% every month."),
            Line(text="Check the order book each evening.", refs=["P3"]),
        ]
    )
    _, _, content = built(ideas=d.ideas)
    issues = brain_docs.check_content(content)
    assert any("section 3" in i for i in issues)
    assert any("Orders get lost" in i and "needs 2" in i for i in issues)
    checked = brain_docs.check_box_draft(d, {"P1", "P2", "P3"})
    assert checked and all("valueLine" in i for i in checked)


def test_a_stored_component_outside_the_catalogue_stops_approval():
    _, _, content = built()
    content["components"][0]["key"] = "custom_crm"
    assert any("approved catalogue" in i for i in brain_docs.check_content(content))


def test_a_hypothesis_with_a_price_or_a_promise_is_caught():
    d = draft(hypotheses=[Line(text="You will save Rs 500,000 a year.", refs=["P1"])])
    _, _, content = built(hypotheses=d.hypotheses)
    text = " ".join(brain_docs.check_content(content))
    assert "price" in text or "R-DOC" in text


def test_a_problem_missing_from_the_order_or_clusters_is_flagged():
    _, _, content = built()
    content["order"] = content["order"][:2]
    content["clusters"] = content["clusters"][:2]
    issues = " ".join(brain_docs.check_content(content))
    assert "P3 is not in the order of work" in issues or "P1 is not in the order" in issues
    assert "is in no cluster" in issues


def test_the_order_puts_a_blocker_first_even_against_the_ranking():
    links = [{"from": "id3", "to": "id2", "type": "blocks", "status": "suggested"}]
    order = box_doc.order_of_work(VIEWS, links)
    refs = [o["ref"] for o in order]
    assert refs.index("P3") < refs.index("P2") == 0 + refs.index("P2")
    assert refs == ["P3", "P2", "P1"]
    assert "comes after" in order[1]["why"] and "Orders get lost" in order[1]["why"]
    cyclic = links + [{"from": "id2", "to": "id3", "type": "blocks", "status": "suggested"}]
    assert len(box_doc.order_of_work(VIEWS, cyclic)) == 3  # a cycle never loses a problem


def test_only_confident_links_are_shown_and_never_a_rejected_one():
    titles = {"a": "Stock runs out", "b": "Orders get lost", "c": "Rent"}
    shown = box_doc.shown_links(
        [
            {"from": "a", "to": "b", "confidence": "0.80", "status": "suggested"},
            {"from": "a", "to": "c", "confidence": "0.60", "status": "suggested"},
            {"from": "b", "to": "c", "confidence": "0.95", "status": "rejected"},
            {
                "from": "b",
                "to": "a",
                "confidence": "0.40",
                "status": "confirmed",
                "evidence": "owner_said",
            },
        ],
        titles,
    )
    assert shown == [
        "Stock runs out and Orders get lost look connected.",
        "Orders get lost and Stock runs out look connected.",
    ]


def test_the_quote_is_by_phase_priced_only_by_the_reviewer():
    _, _, content = built()
    quote = brain_docs.quote_content(content, "PKR")
    assert [p["phase"] for p in quote["phases"]] == [1, 2]
    assert all(p["price"] is None for p in quote["phases"])
    assert quote["phases"][1]["items"] == [
        solutions.build_phrase("order_capture"),
        solutions.build_phrase("dashboards_reports"),
    ]
    assert quote["cost"]["total"] is None
    # the six-section document keeps the quote it always had
    plain = brain_docs.quote_content({"ref": "SD-1", "components": [], "wont_do": []}, "PKR")
    assert "phases" not in plain


def test_phase_prices_must_all_be_set_and_add_up():
    phases = [
        {"phase": 1, "name": "One", "price": "100.00"},
        {"phase": 2, "name": "Two", "price": None},
    ]
    assert box_doc.phase_price_issues({"phases": phases}, Decimal(300)) == [
        "enter the price of Two"
    ]
    phases[1]["price"] = "150.00"
    assert box_doc.phase_price_issues({"phases": phases}, Decimal(300)) == [
        "the phase prices must add up to the total"
    ]
    assert box_doc.phase_price_issues({"phases": phases}, Decimal(250)) == []
    assert box_doc.phase_price_issues({}, Decimal(1)) == []


def test_a_reviewer_prices_each_phase_and_cannot_enter_nonsense():
    _, _, content = built()
    doc = SimpleNamespace(
        kind="quote",
        status="in_review",
        content=brain_docs.quote_content(content, "PKR"),
        total=None,
        currency="PKR",
        valid_until=None,
        drafted_by="pi",
        approved_by=None,
        approved_at=None,
        review_notes="",
    )
    brain_docs.edit(doc, {"phases": [{"phase": 1, "price": "1000"}, {"phase": 2, "price": "2500"}]})
    assert [p["price"] for p in doc.content["phases"]] == ["1000.00", "2500.00"]
    try:
        brain_docs.edit(doc, {"phases": [{"phase": 1, "price": "-5"}]})
    except Exception as refused:
        assert "INVALID_PRICE" in str(getattr(refused, "code", refused))
    else:
        raise AssertionError("a negative price was accepted")


def test_solution_edits_keep_the_catalogue_key_and_phase():
    _, _, content = built()
    doc = SimpleNamespace(
        kind="solution",
        status="in_review",
        content=content,
        drafted_by="pi",
        approved_by=None,
        approved_at=None,
        review_notes="",
    )
    comps = [{**c, "text": c["text"] + " today"} for c in content["components"]]
    brain_docs.edit(doc, {"components": comps, "assumptions": ["One more open question"]})
    assert [c["key"] for c in doc.content["components"]] == [
        "stock_alerts",
        "order_capture",
        "dashboards_reports",
    ]
    assert [c["phase"] for c in doc.content["components"]] == [1, 2, 2]
    assert doc.content["assumptions"] == ["One more open question"]


def test_the_naya_list_is_what_arrived_after_the_box_was_sent():
    current = [{"ref": "P1", "title": "Stock runs out"}, {"ref": "P4", "title": "Rent is due."}]
    titles = box_doc.new_since_sent(["P1", "P2"], current)
    assert titles == ["Rent is due."]
    assert box_doc.naya_line(titles, "roman_ur") == "Naya: Rent is due"
    assert box_doc.naya_line(["a", "b", "c", "d", "e", "f"], "en") == "New: a; b; c; d (+2)"
    assert box_doc.naya_line([], "en") == ""


def test_the_pdf_has_all_eight_sections_and_a_priced_quote_by_phase():
    _, _, content = built()
    content["naya"] = ["Rent is due"]
    pdf = brain_pdf.render_solution(
        content, business="Biz", ref="SD-0001", issued=date(2026, 10, 28), language="en"
    )
    assert pdf.startswith(b"%PDF")
    quote = brain_docs.quote_content(content, "PKR")
    quote["phases"][0]["price"] = "1000.00"
    quote["phases"][1]["price"] = "2500.00"
    out = brain_pdf.render_quote(
        quote,
        business="Biz",
        ref="Q-0001",
        solution_ref="SD-0001",
        issued=date(2026, 10, 28),
        valid_until=date(2030, 1, 1),
        total=Decimal("3500"),
        currency="PKR",
        language="en",
        banks=[],
        phone=None,
    )
    assert out.startswith(b"%PDF")
    # a six-section document is still drawn the old way
    old = brain_pdf.render_solution(
        {"problems": [], "components": [], "covers": [], "wont_do": [], "needs": []},
        business="Biz",
        ref="SD-2",
        issued=date(2026, 10, 28),
        language="en",
    )
    assert old.startswith(b"%PDF")


def test_the_box_is_only_drafted_with_brain_mode_and_box_offer_exactly_true():
    on = {"pi_mode": "brain", "brain": {"box_offer": True}}
    assert box_doc.document_enabled(on)
    assert not box_doc.document_enabled({"pi_mode": "brain", "brain": {"box_offer": "yes"}})
    assert not box_doc.document_enabled({"pi_mode": "brain"})
    assert not box_doc.document_enabled({"brain": {"box_offer": True}})
    assert not box_doc.document_enabled(None)


def test_the_link_floor_is_one_number_everywhere():
    from app.modules.pi import brain_config, taxonomy

    assert Decimal(brain_config.LINK_DEFAULT) / 100 == taxonomy.LINK_SHOWN_AT == Decimal("0.75")
    assert brain_config.LINK_RANGE == (60, 90)
