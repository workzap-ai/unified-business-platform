"""Chapters and key moments: checked in code, timed on the transcript's own clock."""

from types import SimpleNamespace

import pytest

from app.modules.pi_meetings import chapters as ch
from app.modules.pi_meetings.chapters import ChapterDraft, Line


def transcript(count=12):
    return [
        Line(i, i * 10_000, i * 10_000 + 9_000, "Sam" if i % 2 else "Ayesha", f"line {i} text")
        for i in range(count)
    ]


def test_chapters_start_at_real_lines_run_in_order_and_cover_the_meeting():
    lines = transcript()
    drafts = [
        ChapterDraft(start_line=7, title="Delivery", summary="How orders get delivered"),
        ChapterDraft(start_line=2, title="Shop", summary="What the shop sells"),
        ChapterDraft(start_line=999, title="Ghost", summary="No such line"),
        ChapterDraft(start_line=7, title="Again", summary="the same line twice"),
    ]
    items = ch.build_items(drafts, lines)
    assert [i["start_line"] for i in items] == [0, 7]  # the first starts at the first line
    assert items[0]["title"] == "Shop" and items[1]["title"] == "Delivery"
    assert items[0]["start_ms"] == 0 and items[0]["end_ms"] == items[1]["start_ms"] == 70_000
    assert items[1]["end_ms"] == lines[-1].end_ms  # the last runs to the end
    assert all(i["end_ms"] >= i["start_ms"] for i in items)


def test_a_title_or_sentence_with_money_or_contact_details_is_replaced_or_left_out():
    lines = transcript()
    drafts = [
        ChapterDraft(start_line=0, title="Quote Rs 50,000", summary="They will pay 20% less"),
        ChapterDraft(start_line=4, title="Call 03001234567", summary="Ask for ayesha@example.com"),
        ChapterDraft(start_line=8, title="Next steps", summary="Agree who sends the layout"),
    ]
    items = ch.build_items(drafts, lines)
    assert [i["title"] for i in items] == ["Part 1", "Part 2", "Next steps"]
    assert [i["summary"] for i in items] == ["", "", "Agree who sends the layout"]


def test_nothing_usable_or_no_lines_gives_no_chapters_and_the_count_is_capped():
    assert ch.build_items([], transcript()) == []
    assert ch.build_items([ChapterDraft(start_line=50)], transcript()) == []
    assert ch.build_items([ChapterDraft(start_line=0)], []) == []
    many = [ChapterDraft(start_line=i, title=f"Topic {i}") for i in range(12)]
    assert len(ch.build_items(many, transcript())) == ch.MAX_CHAPTERS


def test_a_long_transcript_is_sampled_evenly_for_the_model():
    long = transcript(1000)
    seen = ch.shown(long)
    assert len(seen) <= ch.MAX_LINES_SHOWN and seen[0].ordinal == 0
    assert ch.shown(transcript(10)) == transcript(10)


def finding(kind, text, refs, status="approved", edited=""):
    return SimpleNamespace(
        kind=kind, text=text, edited_text=edited, segment_refs=refs, review_status=status
    )


def test_key_moments_are_only_approved_findings_at_the_time_of_their_first_line():
    times = {0: 0, 3: 30_000, 5: 50_000}
    found = [
        finding("decision", "Start with the shop page", [5, 3]),
        finding("next_step", "Send the layout", [0], status="edited", edited="Send the new layout"),
        finding("decision", "A draft nobody checked", [3], status="pending"),
        finding("problem", "Rejected guess", [3], status="rejected"),
        finding("summary", "A recap is not a moment", [3]),
        finding("action", "Cites nothing", []),
        finding("action", "Cites a gone line", [99]),
        finding("risk", "Pay Rs 5000 first", [3]),
    ]
    out = ch.moments(found, times)
    assert [(m["text"], m["start_ms"], m["line"]) for m in out] == [
        ("Send the new layout", 0, 0),
        ("Start with the shop page", 30_000, 3),
    ]


class Manager:
    def __init__(self, drafts=None, down=False):
        self.drafts, self.down, self.body = drafts or [], down, None

    async def complete_structured(self, scope, schema, **kwargs):
        from app.ai.errors import GatewayUnavailable

        if self.down:
            raise GatewayUnavailable("down")
        self.body = kwargs["messages"][-1].content
        return SimpleNamespace(value=schema(chapters=self.drafts))


async def test_make_returns_checked_chapters_and_a_failed_model_stores_nothing():
    lines = transcript()
    good = Manager(
        [ChapterDraft(start_line=0, title="Hello"), ChapterDraft(start_line=6, title="Plan")]
    )
    made = await ch.make(good, None, lines, "en")
    assert [i["title"] for i in made["items"]] == ["Hello", "Plan"] and made["made_at"]
    assert "line 0 text" in good.body
    with pytest.raises(ch.ChaptersFailed):
        await ch.make(Manager(down=True), None, lines, "en")
    with pytest.raises(ch.ChaptersFailed):  # an answer with no usable chapter is a failure too
        await ch.make(Manager([ChapterDraft(start_line=500)]), None, lines, "en")
