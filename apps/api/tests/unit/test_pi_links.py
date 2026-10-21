"""Links a customer sends are found, recognised and summarised safely."""

import pytest

from app.modules.pi.links import link_note, links_in, youtube_id


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/shorts/TuLe2t8h1KI", "TuLe2t8h1KI"),
        ("https://youtube.com/watch?v=dQw4w9WgXcQ&t=10", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?si=abc", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/@somechannel", None),
        ("https://example.com/watch?v=dQw4w9WgXcQ", None),
    ],
)
def test_youtube_ids(url: str, expected: str | None) -> None:
    assert youtube_id(url) == expected


def test_links_are_found_once_without_trailing_punctuation() -> None:
    text = "see https://a.example/x, and https://a.example/x and (https://b.example/y). ok"
    assert links_in(text) == ["https://a.example/x", "https://b.example/y"]
    assert links_in("no links here") == []
    assert len(links_in(" ".join(f"https://e{i}.example" for i in range(5)))) == 2


def test_link_note_marks_unreadable_links() -> None:
    note = link_note(
        [
            {"url": "https://a.example", "title": "Booking demo", "summary": "A booking app"},
            {"url": "https://b.example", "unreadable": True},
        ]
    )
    assert "[Link Booking demo: A booking app]" in note
    assert "[Link https://b.example: could not be opened]" in note
