"""Recording parts: how a transcribed part becomes timed segments (no database, no model)."""

from app.modules.pi_meetings.recording_routes import (
    PART_STRIDE,
    SEGMENT_CHARS,
    split_sentences,
    timed,
)


def test_sentences_split_on_latin_and_urdu_punctuation():
    pieces = split_sentences("Hello there. How is stock?  Theek hai۔ Aap kaise hain؟ Fine")
    assert pieces == ["Hello there.", "How is stock?", "Theek hai۔", "Aap kaise hain؟", "Fine"]


def test_a_long_run_without_punctuation_is_cut_at_word_boundaries():
    words = ("stock " * 600).strip()
    pieces = split_sentences(words)
    assert len(pieces) > 1
    assert all(0 < len(p) <= SEGMENT_CHARS for p in pieces)
    assert " ".join(pieces) == words  # nothing lost, nothing duplicated


def test_empty_and_blank_text_gives_no_pieces():
    assert split_sentences("") == []
    assert split_sentences("   \n  ") == []


def test_timing_is_proportional_ordered_and_offset_by_the_part_start():
    spans = timed(["aaaa", "bb", "cccccc"], offset_ms=300_000, duration_ms=12_000)
    assert [w for _, _, w in spans] == ["aaaa", "bb", "cccccc"]
    assert spans[0][0] == 300_000
    assert spans[-1][1] == 312_000  # the last piece ends where the part ends
    for (_, end, _), (start, _, _) in zip(spans, spans[1:], strict=False):
        assert start == end  # contiguous, never overlapping
    assert all(end >= start for start, end, _ in spans)


def test_a_part_never_needs_more_ordinals_than_it_reserves():
    assert PART_STRIDE >= 500  # a part is a few minutes of speech
