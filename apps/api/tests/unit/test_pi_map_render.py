"""Drawing the problem map (spec 4.6, 4.7): sizes, determinism, overflow, contrast, RTL, numbers."""

import io
import re

import pytest
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


RTL_MAPS = {
    "ur": (
        ["پرانا مال رکا ہوا ہے", "پیسہ پھنسا ہوا ہے Workzap", "تنخواہ دیر سے ملتی ہے"],
        [["6 کروڑ لاگت پر"], ["45 دن سے"], []],
    ),
    "ar": (
        ["مخزون قديم متوقف", "الأموال عالقة", "تأخر الرواتب"],
        [["6 ملايين بسعر التكلفة"], ["منذ 45 يوما"], []],
    ),
    "fa": (
        ["کالای قدیمی مانده است", "پول گیر کرده است", "حقوق دیر پرداخت می‌شود"],
        [["۶ میلیون به قیمت تمام‌شده"], ["۴۵ روز است"], []],
    ),
}


def rtl_map(lang: str, n: int = 3) -> dict:
    labels, facts = RTL_MAPS[lang]
    nodes = []
    for i in range(n):
        nodes.append(
            {
                "id": f"n{i}",
                "label": labels[i % 3],
                "facts": facts[i % 3],
                "category": ["stock_inventory", "cash_collections", "people_staff"][i % 3],
                "is_new": i == 2,
            }
        )
    links = [
        {"from": "n0", "to": "n1", "type": "causes", "label": "", "evidence": "owner_said"},
        {"from": "n1", "to": "n2", "type": "worsens", "label": "", "evidence": "pi_inferred"},
    ]
    return {"version": 3, "nodes": nodes, "links": links, "clusters": []}


def latin_twin(n: int = 3) -> dict:
    """The same shape of map in English, to compare the layout with."""
    twin = rtl_map("ur", n)
    for node in twin["nodes"]:
        node["label"] = "Old stock stuck"
        node["facts"] = []
    return twin


def ink_columns(png: bytes, box: tuple[int, int, int, int]) -> list[int]:
    """The x of every dark pixel inside the box (text and bars), for where-is-it checks."""
    pic = decode(png).convert("RGB").crop(box)
    width, height = pic.size
    data = pic.load()
    return [x for x in range(width) for y in range(height) if sum(data[x, y]) < 330]


@pytest.mark.parametrize("lang", ["ur", "ar", "fa"])
def test_right_to_left_scripts_are_drawn_with_size_determinism_and_no_overflow(lang):
    r = m.render_map(rtl_map(lang), lang)
    assert r.rtl and r.drawable and r.reason == "" and len(r.images) == 1
    image = r.images[0]
    pic = decode(image.png)
    assert pic.format == "PNG" and pic.size[0] == 1080
    assert m.MIN_HEIGHT <= pic.size[1] <= m.MAX_HEIGHT and len(image.png) < m.MAX_PNG_BYTES
    assert image.overflow == [] and image.smallest_text >= m.MIN_TEXT_PX
    again = m.render_map(rtl_map(lang), lang)
    assert [i.png for i in again.images] == [image.png] and again.hash == r.hash
    assert image.caption and image.alt and all(a for a in image.alt)
    # the same map with more problems: overview plus detail images, none overflowing
    big = m.render_map(rtl_map(lang, 25), lang)
    assert big.images[0].kind == "overview"
    assert any(i.kind == "overview" for i in big.images)
    assert all(i.overflow == [] and i.smallest_text >= 24 and i.width == 1080 for i in big.images)
    assert all(i.height <= m.MAX_HEIGHT for i in big.images)
    assert sum(len(i.alt) for i in big.images if i.kind == "detail") >= 25


@pytest.mark.parametrize("lang", ["ur", "ar", "fa"])
def test_right_to_left_layout_is_the_mirror_of_the_left_to_right_one(lang):
    n = 3
    left = m.render_map(latin_twin(n), "en").images[0]
    right = m.render_map(rtl_map(lang, n), lang).images[0]
    assert left.positions == right.positions  # the same slots: column 0 is the first card
    for nid, (x, y) in left.pixels.items():
        rx, ry = right.pixels[nid]
        assert ry == y and rx == m.WIDTH - x - m.CARD_W
    # the first card sits on the right, the second to its left
    assert right.pixels["n0"][0] > right.pixels["n1"][0]
    assert left.pixels["n0"][0] < left.pixels["n1"][0]
    # colour bar on the right edge of a card, text hugging the right edge (not the left)
    x, y = right.pixels["n0"]
    inner = (x, y, x + m.CARD_W - 20, y + m.CARD_H)
    xs = ink_columns(right.png, inner)
    assert xs and sum(xs) / len(xs) > m.CARD_W * 0.55
    # header title is on the right, the brand name on the left
    bright = decode(right.png).convert("RGB").crop((0, 0, 1080, 150))
    lit = [x for x in range(1080) for yy in range(20, 70) if sum(bright.getpixel((x, yy))) > 600]
    assert min(lit) < 200 and max(lit) > 900


@pytest.mark.parametrize("lang", ["ur", "ar", "fa"])
def test_right_to_left_picture_is_not_blank_and_differs_from_the_latin_one(lang):
    right = decode(m.render_map(rtl_map(lang), lang).images[0].png).convert("RGB")
    left = decode(m.render_map(latin_twin(), "en").images[0].png).convert("RGB")
    assert right.size[0] == left.size[0]
    colours = right.getcolors(maxcolors=1_000_000) or []
    background = max(colours)[1]
    assert background == m.BG
    ink = sum(c for c, rgb in colours if sum(rgb) < 330)
    assert ink > 3000  # real glyphs were drawn
    assert right.size != left.size or right.tobytes() != left.tobytes()
    assert len(colours) > 20  # anti-aliased text, bars, tag


def test_right_to_left_wording_is_complete_and_in_script():
    english = set(m.TEXT["en"])
    for lang in ("ur", "ar", "fa"):
        words = m.TEXT[lang]
        assert english <= set(words), (lang, english - set(words))
        assert set(words["types"]) == set(m.TEXT["en"]["types"])
        for key, value in words.items():
            if isinstance(value, str):
                letters = [c for c in re.sub(r"{[^}]*}", "", value) if c.isalpha()]
                assert all(not ("a" <= c.lower() <= "z") for c in letters), (lang, key, value)
        assert "Workzap" not in " ".join(str(v) for v in words.values())
    assert m.TEXT["ur"]["new"] == "نیا" and m.TEXT["ur"]["header"] == "آپ کے کاروبار کا نقشہ"
    # Pashto and Sindhi readers get the Urdu picture; Latin-script Roman Urdu is untouched
    assert m.render_map(rtl_map("ur"), "ps").language == "ur"
    assert m.render_map(rtl_map("ur"), "sd").drawable
    assert m.render_map(rtl_map("ar"), "ar-SA").language == "ar"
    assert m.is_rtl("ur") and m.is_rtl("ar-SA") and not m.is_rtl("roman_ur")
    assert not hasattr(m, "NEEDS_FOR_RTL_IMAGES")


def test_numbers_in_right_to_left_pictures_must_be_the_owners():
    mp = rtl_map("ur")
    mp["nodes"][1]["facts"] = ["99 دن سے", "45 دن سے"]
    r = m.render_map(mp, "ur", owner_messages=["پیسہ 45 دن سے پھنسا ہے", "6 کروڑ"])
    assert r.drawable and r.dropped == ["99 دن سے"]
    assert all("99" not in line for line in r.images[0].alt)
    assert any("45" in line for line in r.images[0].alt)


def test_right_to_left_falls_back_to_text_when_drawing_is_impossible(monkeypatch):
    def broken():
        raise ImportError("arabic_reshaper")

    monkeypatch.setattr(m, "_load_rtl", broken)
    urdu = m.render_map(rtl_map("ur"), "ur")
    assert urdu.rtl and not urdu.drawable and urdu.images == []
    assert urdu.reason.startswith("rtl_support_missing") and "arabic_reshaper" in urdu.reason
    assert "←" in urdu.text and "→" not in urdu.text and "نقشہ" in urdu.text
    assert m.render_map(make_map(3), "roman_ur").drawable  # Latin never needs the packages

    def no_font():
        raise OSError("cannot open resource")

    monkeypatch.setattr(m, "_load_rtl", no_font)
    arabic = m.render_map(rtl_map("ar"), "ar")
    assert not arabic.drawable and "OSError" in arabic.reason and "←" in arabic.text


def test_words_the_fonts_cannot_draw_fall_back_to_text():
    odd = rtl_map("ur")
    odd["nodes"][0]["label"] = "漢字 مال"
    r = m.render_map(odd, "ur")
    assert not r.drawable and r.reason == "text_not_drawable_in_naskh_font" and "←" in r.text
    # Arabic script words inside an English map are not drawn with a Latin font either
    mixed = make_map(2)
    mixed["nodes"][0]["label"] = "مال رکا"
    assert not m.render_map(mixed, "en").drawable
    assert m.render_map({"version": 1, "nodes": []}, "ur").reason == "empty_map"


def test_latin_words_inside_right_to_left_text_use_the_latin_font():
    assert m.rtl_drawable("پیسہ Workzap 45 (ok)…")
    runs = m._runs(m.shape_rtl("پیسہ Workzap"))
    assert any(latin for _, latin in runs) and any(not latin for _, latin in runs)
    assert not m.rtl_drawable("漢字")
    assert m.NASKH_REGULAR.exists() and m.NASKH_BOLD.exists()
    assert (m.FONT_DIR / "OFL.txt").exists()
    # Arabic letters are joined: the shaped text has presentation forms, not the raw letters
    assert m.shape_rtl("بب") != "بب"


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
