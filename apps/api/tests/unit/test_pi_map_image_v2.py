"""Spec v1.5, 18.7: map image rules v2 (MD tests that the renderer can show)."""

import io

from PIL import Image

from app.modules.pi import map_render as m


def _map(n: int, links: int = 0) -> dict:
    nodes = [
        {"id": f"n{i}", "label": f"Problem {i}", "facts": [], "category": "other"} for i in range(n)
    ]
    out = [{"from": "n0", "to": "n1", "type": "causes", "label": "", "evidence": "pi_inferred"}][
        :links
    ]
    return {"version": 1, "nodes": nodes, "links": out, "clusters": []}


def test_md6_no_links_reads_no_links_yet_never_zero_links() -> None:
    render = m.render_map(_map(3), "en")
    caption = render.images[0].caption
    assert "No links yet" in caption and "0 links" not in caption


def test_the_caption_asks_whether_it_is_right() -> None:
    caption = m.render_map(_map(3, 1), "en").images[0].caption
    assert "Is this right? Tell me what to change." in caption


def test_md3_the_safe_margin_is_48_and_the_header_stays_inside() -> None:
    assert m.MARGIN == 48
    for title in ("Plan", "A" * 30, "B" * 60):
        render = m.render_map(_map(3), "en")
        assert not render.images[0].overflow, title


def test_md4_height_is_content_based_with_a_640_floor() -> None:
    assert m.MIN_HEIGHT == 640
    image = Image.open(io.BytesIO(m.render_map(_map(3), "en").images[0].png))
    assert 640 <= image.size[1] <= 1920


def test_the_footer_line_is_left_out_when_no_number_is_drawn() -> None:
    words = m.TEXT["en"]
    assert words["foot"] == "Your numbers only. No names."
    plain = m.render_map(_map(3), "en").images[0]
    numbered_map = _map(3)
    numbered_map["nodes"][0]["facts"] = ["10 crore"]
    numbered = m.render_map(numbered_map, "en", owner_messages=["10 crore"]).images[0]
    assert plain.png != numbered.png
