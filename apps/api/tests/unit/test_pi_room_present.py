"""What pi presents in a room: the recap slides, the state machine and the picture of a slide."""

import numpy as np

from app.modules.pi_meetings import room_present as rp
from app.modules.pi_meetings import slide_render as sr

EARLIER = [
    {
        "when": "2026-11-12",
        "points": [
            "next_step: Send the layout (by Friday)",
            "decision: Start with the shop page",
            "problem: Orders get missed on busy days",
        ],
    },
    {"when": "2026-10-30", "points": ["summary: They sell cloth and want online orders"]},
]


def test_the_recap_is_built_from_approved_points_and_todays_notes() -> None:
    slides = rp.build(EARLIER, ["They need delivery in Lahore"])
    assert [s["heading"] for s in slides] == [
        rp.TITLE,
        "Our call on 12 November 2026",
        "Our call on 30 October 2026",
        "Noted in today's call",
        rp.CLOSING,
    ]
    assert slides[1]["bullets"][0] == "Next step: Send the layout (by Friday)"
    assert slides[1]["bullets"][1] == "Decided: Start with the shop page"
    assert slides[0]["kind"] == slides[-1]["kind"] == "title"
    assert len(slides) <= rp.MAX_SLIDES


def test_a_line_with_a_price_or_contact_detail_is_left_out_and_nothing_means_nothing_to_show():
    slides = rp.build(
        [
            {
                "when": "2026-11-12",
                "points": ["decision: Pay Rs 50,000 first", "next_step: Call 03001234567"],
            }
        ],
        ["They want a 20% discount", "They need a logo"],
    )
    text = " ".join(" ".join(s["bullets"]) for s in slides)
    assert "50,000" not in text and "03001234567" not in text and "discount" not in text
    assert "They need a logo" in text and "Our call on" not in " ".join(
        s["heading"] for s in slides
    )
    assert rp.build([], []) == []
    assert rp.build([{"when": "2026-11-12", "points": ["decision: Pay Rs 50,000"]}], []) == []


def test_the_state_machine_moves_within_the_slides_and_stops_cleanly() -> None:
    slides = rp.build(EARLIER, [])
    state = rp.start(slides, {})
    assert state["on"] and state["index"] == 0 and state["v"] == 1
    assert rp.go(state, step=1)["index"] == 1
    assert rp.go(state, step=-5)["index"] == 0  # never before the first
    assert rp.go(state, step=99)["index"] == len(slides) - 1  # nor past the last
    assert rp.go(state, index=2)["index"] == 2
    again = rp.start(slides, state)
    assert again["v"] == 2  # a new start is told apart from the old one
    ended = rp.stop(again)
    assert ended["on"] is False and ended["slides"] == [] and ended["v"] == 2
    assert rp.go(ended, step=1) == ended  # nothing on show: nothing moves
    assert rp.go(None, step=1) == {}


def test_the_summary_for_the_page_names_the_slide_on_show() -> None:
    state = rp.go(rp.start(rp.build(EARLIER, []), {}), step=1)
    assert rp.summary(state) == {
        "on": True,
        "index": 1,
        "total": 4,
        "heading": "Our call on 12 November 2026",
    }
    assert rp.summary({}) == {"on": False, "index": 0, "total": 0, "heading": ""}
    assert rp.summary(rp.stop(state))["on"] is False


def pixels(image):
    return np.asarray(image)


def test_a_slide_is_a_720p_picture_with_something_drawn_on_it() -> None:
    slides = rp.build(EARLIER, [])
    for number, slide in enumerate(slides, start=1):
        image = sr.render(slide, number, len(slides))
        assert image.size == (sr.WIDTH, sr.HEIGHT) and image.size[0] % 2 == image.size[1] % 2 == 0
        assert (pixels(image) != 255).any()
    assert pixels(sr.render(slides[1], 2, 5))[10, 10].tolist() == list(sr.BRAND)  # the header band


def test_text_that_is_too_long_shrinks_and_never_runs_over_the_footer() -> None:
    long_bullets = [f"Next step: a rather long point number {i} " * 4 for i in range(12)]
    slide = {"kind": "content", "heading": "A very long heading " * 6, "bullets": long_bullets}
    picture = pixels(sr.render(slide, 3, 5))
    gap = picture[sr.BODY_BOTTOM + 6 : sr.FOOTER_Y - 38]  # between the body and the footer line
    assert (gap == 255).all()


def test_an_urdu_slide_is_drawn_right_to_left_with_its_bullet_on_the_right() -> None:
    slide = {
        "kind": "content",
        "heading": "ہماری پچھلی بات",
        "bullets": ["اگلا قدم: ہفتے تک ڈیزائن بھیجنا", "فیصلہ: پہلے دکان کا صفحہ بنانا"],
    }
    picture = pixels(sr.render(slide, 2, 3))
    body = picture[sr.BODY_TOP : sr.BODY_BOTTOM]
    dark = np.where((body < 200).any(axis=2))  # columns of drawn pixels
    middle = sr.WIDTH // 2
    assert dark[1].size > 0
    assert (dark[1] > middle).sum() > (dark[1] < middle).sum()  # the weight is on the right
    mixed = {"kind": "content", "heading": "Mix", "bullets": ["Next step: ڈیزائن بھیجنا Friday"]}
    assert (pixels(sr.render(mixed, 1, 1)) != 255).any()


def test_wrapping_never_splits_a_word_and_keeps_every_word() -> None:
    text = "one two three four five six seven eight nine ten"
    lines = sr.wrap(text, 34, 300)
    assert len(lines) > 1 and " ".join(lines) == text
    assert all(sr.width_of(line, 34) <= 300 for line in lines)
    assert sr.wrap("", 34, 300) == [""]
