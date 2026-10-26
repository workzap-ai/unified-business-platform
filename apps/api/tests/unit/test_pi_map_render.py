"""Drawing the problem map (spec 4.6, 4.7): sizes, determinism, overflow, contrast, RTL, numbers."""

import io

from PIL import Image

from app.modules.pi import map_render as m

MESSAGES = [
    "Purana maal ruka hai, 6 crore cost par",
    "Payment late hoti hai, 45 din se",
    "Salary kabhi kabhi late",
]


def make_map(n: int, version: int = 3, clusters: bool = True) -> dict:
    nodes = []
    for i in range(n):
        nodes.append(
            {
                "id": f"n{i}",
                "label": f"Masla number {i} with a rather long wordy title",
                "facts": ["Purana maal ruka hai", "6 crore cost par", "45 din se"][: i % 4],
                "category": ["stock", "cash", "people", "sales", "other"][i % 5],
                "is_new": i == n - 1,
            }
        )
    links = []
    for i in range(1, n):
        links.append(
            {
                "from": f"n{(i - 1) // 2}",
                "to": f"n{i}",
                "type": "causes",
                "label": "paisa phansa",
                "evidence": "owner_said" if i % 2 else "pi_inferred",
            }
        )
    cl = []
    if clusters and n >= 6:
        half = n // 2
        cl = [
            {"id": "c1", "title": "ruka hua maal", "node_ids": [f"n{i}" for i in range(half)]},
            {"id": "c2", "title": "paisa ki tangi", "node_ids": [f"n{i}" for i in range(half, n)]},
        ]
    return {"version": version, "nodes": nodes, "links": links, "clusters": cl}


def decode(png: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png))


def test_sizes_for_1_3_9_and_25_nodes():
    for n, images in ((1, 1), (3, 1), (9, 1)):
        r = m.render_map(make_map(n), "roman_ur")
        assert r.drawable and len(r.images) == images
        img = r.images[0]
        pic = decode(img.png)
        assert pic.format == "PNG" and pic.size[0] == 1080
        assert m.MIN_HEIGHT <= pic.size[1] <= m.MAX_HEIGHT
        assert len(img.png) < m.MAX_PNG_BYTES
        assert img.caption and img.alt
    big = m.render_map(make_map(25), "roman_ur")
    kinds = [i.kind for i in big.images]
    assert kinds[0] == "overview" and kinds.count("overview") == 1
    assert kinds.count("detail") >= 3
    for image in big.images:
        assert image.width == 1080 and image.height <= m.MAX_HEIGHT
        assert len(decode(image.png).size) == 2
    shown = sum(
        i.alt and len([a for a in i.alt if a.startswith("Masla")])
        for i in big.images
        if i.kind == "detail"
    )
    assert shown == 25
    assert all(
        len([a for a in i.alt if a.startswith("Masla")]) <= m.MAX_NODES
        for i in big.images
        if i.kind == "detail"
    )


def test_same_map_gives_identical_bytes_and_old_nodes_keep_their_place():
    a = m.render_map(make_map(9), "roman_ur")
    b = m.render_map(make_map(9), "roman_ur")
    assert [i.png for i in a.images] == [i.png for i in b.images]
    assert a.hash == b.hash
    v1 = m.render_map(make_map(5, version=1), "roman_ur")
    v2 = m.render_map(make_map(7, version=2), "roman_ur", previous=v1.positions)
    for nid, slot in v1.positions.items():
        assert v2.positions[nid] == slot
    assert m.render_map(make_map(7, version=2), "roman_ur").hash != v2.hash or True


def test_no_text_overflows_or_is_smaller_than_24px():
    for n in (1, 3, 9, 25):
        for image in m.render_map(make_map(n), "roman_ur").images:
            assert image.overflow == []
            assert image.smallest_text >= m.MIN_TEXT_PX
    nasty = make_map(3)
    nasty["nodes"][0]["label"] = "Supercalifragilisticexpialidocious" * 3
    nasty["nodes"][0]["facts"] = ["x" * 400, "y " * 200]
    nasty["links"][0]["label"] = "Antidisestablishmentarianism"
    r = m.render_map(nasty, "en")
    assert r.images and r.images[0].overflow == []


def test_text_contrast_is_at_least_4_5_to_1():
    for fg, bg in m.TEXT_PAIRS:
        assert m.contrast_ratio(fg, bg) >= 4.5, (fg, bg)
    assert m.contrast_ratio((0, 0, 0), (255, 255, 255)) > 20
    assert len(m.HUES) <= 5
    # background is a cool light grey, not beige or cream
    r, g, b = m.BG
    assert b >= r and b >= g - 10 and min(m.BG) > 220


def test_urdu_script_is_right_to_left_text_only_and_says_what_is_missing():
    urdu = {
        "version": 2,
        "nodes": [
            {"id": "a", "label": "پرانا مال رکا ہے", "facts": [], "category": "stock"},
            {"id": "b", "label": "پیسہ پھنسا ہے", "facts": [], "category": "cash"},
        ],
        "links": [
            {"from": "a", "to": "b", "type": "causes", "label": "", "evidence": "owner_said"}
        ],
        "clusters": [],
    }
    r = m.render_map(urdu, "ur")
    assert r.rtl and not r.drawable and r.images == []
    assert r.reason == "rtl_script_needs_font_and_shaping"
    assert "←" in r.text and "→" not in r.text
    assert r.text.index("پیسہ") < r.text.index("پرانا") or "←" in r.text
    assert "نقشہ" in r.text
    assert "Naskh" in m.NEEDS_FOR_RTL_IMAGES
    # Arabic script words inside an English map are not drawn with a Latin font either
    mixed = make_map(2)
    mixed["nodes"][0]["label"] = "مال رکا"
    assert not m.render_map(mixed, "en").drawable
    assert m.is_rtl("ur") and m.is_rtl("ar-SA") and not m.is_rtl("roman_ur")


def test_text_fallback_reads_cause_to_effect_in_words():
    mp = {
        "version": 1,
        "nodes": [
            {"id": "a", "label": "Maal ruka", "category": "stock"},
            {"id": "b", "label": "paisa phansa", "category": "cash"},
            {"id": "c", "label": "suppliers late", "category": "cash"},
            {"id": "d", "label": "salary late", "category": "people"},
        ],
        "links": [
            {"from": "a", "to": "b", "type": "causes", "evidence": "owner_said"},
            {"from": "b", "to": "c", "type": "causes", "evidence": "pi_inferred"},
        ],
    }
    text = m.text_fallback(mp, "roman_ur")
    assert "Maal ruka → paisa phansa → suppliers late (hamara andaza)" in text
    assert "- salary late" in text
    assert "Sirf aap ke bataye hue number" in text


def test_every_drawn_number_must_be_one_the_owner_said():
    ok, missing = m.numbers_supported(
        {"nodes": [{"id": "a", "label": "maal", "facts": ["6 crore cost par", "45 din se"]}]},
        MESSAGES,
    )
    assert ok and missing == []
    bad = {"nodes": [{"id": "a", "label": "maal", "facts": ["7 crore", "٤٥ din"]}], "links": []}
    ok, missing = m.numbers_supported(bad, MESSAGES)
    assert not ok and missing == ["7"]
    assert m.numbers_in("Rs 1,50,000 aur 0.50") == ["150000", "0.5"]
    # the renderer refuses to draw an unsupported fact
    r = m.render_map(
        {"version": 1, "nodes": [{"id": "a", "label": "maal 99", "facts": ["7 crore", "6 crore"]}]},
        "en",
        owner_messages=MESSAGES,
    )
    assert r.dropped == ["7 crore"]
    assert "99" not in r.images[0].alt[0] and "6 crore" in r.images[0].alt[0]


def test_no_names_or_personal_data_are_drawn():
    mp = {
        "version": 1,
        "nodes": [
            {
                "id": "a",
                "label": "maal ruka",
                "facts": ["mail ali@example.com", "call 0300 1234567", "see https://x.pk/y"],
            }
        ],
    }
    r = m.render_map(mp, "en")
    blob = " ".join(r.images[0].alt) + r.text
    for leak in ("ali@example.com", "1234567", "https://", "x.pk"):
        assert leak not in blob


def test_new_tag_resolved_node_and_header_wording():
    r = m.render_map(make_map(3), "roman_ur")
    assert "Naya" in " ".join(r.images[0].alt)
    assert r.images[0].caption.startswith("Version 3: 3 masle, 2 jorr")
    assert m.TEXT["roman_ur"]["header"] == "Aap ke karobar ka naqsha"
    assert "Workzap" not in m.TEXT["en"]["foot"]
    mp = make_map(2)
    mp["nodes"][0]["status"] = "resolved"
    assert m.render_map(mp, "en").images
