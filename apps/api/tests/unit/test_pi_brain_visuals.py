"""Drawing and signing the pictures of spec 8.11.2."""

import time
from types import SimpleNamespace
from uuid import uuid4

from pydantic import SecretStr

from app.modules.pi import brain_visuals as v
from app.modules.pi.problems import SHOW_ME, summary_due


def rows(n: int = 3):
    return [
        SimpleNamespace(
            category="stock_inventory" if i % 2 == 0 else "people_staff",
            user_words=[f"words number {i}"],
            title=f"Problem number {i} with a rather long title indeed",
        )
        for i in range(n)
    ]


def test_a_token_names_one_conversation_and_expires_or_fails_when_forged(settings):
    s = settings.model_copy(
        update={"secrets_encryption_key": SecretStr("unit-test-key-0123456789abcdef")}
    )
    cid = uuid4()
    value = v.token(s, cid, "board", "roman_ur")
    claims = v.read(s, value)
    assert claims is not None and claims["conversation_id"] == cid
    assert claims["kind"] == "board" and claims["language"] == "roman_ur"
    assert v.read(s, value[:-2] + "xx") is None
    assert v.read(s, "nonsense") is None
    assert v.read(s, v.token(s, cid, "progress", "en", 9))["step"] == 3  # clamped
    old = v.token(s, cid, "board", "en")
    assert v.read(s, old) is not None
    real = time.time
    try:
        time.time = lambda: real() + v.VISUAL_SECONDS + 5  # type: ignore[assignment]
        assert v.read(s, old) is None
    finally:
        time.time = real  # type: ignore[assignment]


def test_the_pictures_are_png_and_only_latin_script_languages_get_one():
    board = v.render_board(v.groups_of(rows(), "en"), "en", "Khan Traders")
    assert board[:8] == b"\x89PNG\r\n\x1a\n"
    assert v.render_progress(1, "roman_ur")[:8] == b"\x89PNG\r\n\x1a\n"
    assert v.supported("en") and v.supported("roman_ur") and v.supported(None)
    assert not v.supported("ar") and not v.supported("ur")


def test_groups_are_biggest_first_with_the_persons_own_words_and_the_list_is_capped():
    groups = v.groups_of(rows(5), "en")
    assert [g.count for g in groups] == [3, 2]
    assert groups[0].words and groups[0].words[0].startswith("words number")
    options = v.list_rows(rows(14))
    assert len(options) == 10  # WhatsApp allows ten rows
    assert all(len(o["title"]) <= 24 and len(o["description"]) <= 72 for o in options)


def test_asking_to_see_what_has_been_noted_brings_the_summary():
    for text in ("show me what you have", "what have you noted so far?", "kya note kiya"):
        assert SHOW_ME.search(text), text
        assert summary_due(text, 2, 0) == "show"
    assert summary_due("show me the weather", 2, 0) is None
    assert summary_due("show me what you have", 0, 0) is None  # nothing noted: nothing to show
