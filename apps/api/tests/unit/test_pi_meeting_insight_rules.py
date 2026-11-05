"""What a meeting insight may say, enforced in code (pi_meetings/insight_rules.py)."""

from app.modules.pi_meetings.insight_rules import MAX_INSIGHTS, Segment, validate

SEGMENTS = [
    Segment(0, "hamari dukaan mein stock khatam ho jata hai", "Speaker 1"),
    Segment(1, "ok, I will send the list by Friday", "Speaker 2"),
    Segment(2, "my number is 0311 2546598", "Speaker 1"),
]
SPEAKERS = ["Speaker 1", "Speaker 2"]


def item(**kw):
    base = {"kind": "problem", "basis": "stated", "text": "stock runs out", "segment_refs": [0]}
    return base | kw


def keep(*items, speakers=SPEAKERS):
    return validate(list(items), SEGMENTS, speakers)


def test_a_stated_item_with_a_real_source_is_kept():
    kept, dropped = keep(item(confidence=90))
    assert dropped == [] and kept[0].segment_refs == [0] and kept[0].confidence == 90


def test_a_stated_item_must_cite_a_segment_that_exists():
    for refs in ([], [99], ["x"], None):
        kept, dropped = keep(item(segment_refs=refs))
        assert kept == [] and dropped == ["stated_without_source"]


def test_an_unknown_kind_or_basis_is_dropped_and_never_raises():
    kept, dropped = keep(
        item(kind="gossip"), item(basis="certain"), "not an item", {"kind": None}, item(text="")
    )
    assert kept == []
    assert dropped.count("unknown_kind_or_basis") == 4 and dropped.count("empty_text") == 1


def test_an_ai_conclusion_never_carries_an_owner_or_a_deadline():
    for basis in ("inferred", "estimate", "recommendation"):
        kept, _ = keep(item(basis=basis, owner_label="Speaker 1", due_text="by Friday"))
        assert kept[0].owner_label == "" and kept[0].due_text == ""


def test_an_ai_conclusion_never_carries_a_price():
    for text in ("it will cost Rs 5,000", "about PKR 5000 a month", "roughly $20", "5000 rs"):
        kept, dropped = keep(item(basis="estimate", text=text))
        assert kept == [] and dropped == ["price_in_ai_conclusion"], text
    kept, _ = keep(item(basis="estimate", text="about 3 weeks of work"))
    assert len(kept) == 1  # time and volume estimates are fine; money is the reviewer's


def test_a_stated_price_is_a_record_of_what_was_said_not_pi_pricing():
    kept, dropped = keep(item(kind="commitment", text="customer said budget is Rs 5000"))
    assert dropped == [] and len(kept) == 1


def test_a_stated_owner_must_be_a_labelled_speaker_or_a_role():
    kept, _ = keep(item(segment_refs=[1], owner_label="speaker 2"))
    assert kept[0].owner_label == "Speaker 2"
    kept, _ = keep(item(segment_refs=[1], owner_label="customer"))
    assert kept[0].owner_label == "Customer"
    kept, _ = keep(item(segment_refs=[1], owner_label="Ahmed"))  # a guessed name
    assert kept[0].owner_label == ""


def test_a_stated_deadline_must_appear_in_the_cited_words():
    kept, _ = keep(item(kind="commitment", segment_refs=[1], due_text="Friday"))
    assert kept[0].due_text == "Friday"
    kept, _ = keep(item(kind="commitment", segment_refs=[1], due_text="next Monday"))
    assert kept[0].due_text == ""


def test_text_is_redacted_before_it_is_kept():
    kept, _ = keep(item(segment_refs=[2], text="customer shared phone 0311 2546598"))
    assert "2546598" not in kept[0].text


def test_a_summary_without_a_source_is_never_stated():
    kept, dropped = keep(item(kind="summary", segment_refs=[], text="a call about stock"))
    assert dropped == [] and kept[0].basis == "inferred"


def test_duplicates_are_dropped_and_the_list_is_capped():
    kept, dropped = keep(item(), item(text="  Stock RUNS out "))
    assert len(kept) == 1 and dropped == ["duplicate"]
    many = [item(text=f"problem {n}") for n in range(MAX_INSIGHTS + 5)]
    kept, dropped = keep(*many)
    assert len(kept) == MAX_INSIGHTS and "too_many" in dropped


def test_confidence_is_clamped_and_bad_values_become_zero():
    kept, _ = keep(
        item(confidence=500), item(text="b", confidence=-5), item(text="c", confidence="x")
    )
    assert [i.confidence for i in kept] == [100, 0, 0]
