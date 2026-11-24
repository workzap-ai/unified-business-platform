"""The room's own speech-to-text, in its pure parts: words become lines, the provider's file names
say who spoke, the captions language is only ever one the provider knows, and the provider's reply
is read safely."""

import asyncio

import httpx

from app.ai.providers.openai import _words
from app.ai.types import Word
from app.modules.pi_meetings import room_provider as rp
from app.modules.pi_meetings.native_stt import GAP_S, MAX_LINE_CHARS, sentences

CALL = "r" + "a" * 32
STAFF = "s_" + "b" * 32
GUEST = "g_" + "c" * 32
UUID = "11111111-2222-3333-4444-555555555555"
CDN = "https://us-east.stream-io-cdn.com/1735428/video/individual_recordings/x.mkv"


def w(text, start, end):
    return Word(text, start, end)


def test_a_line_ends_at_a_full_stop_in_any_script():
    words = [
        w("Hello", 0, 0.4),
        w("there.", 0.5, 0.9),
        w("ہمارا", 1.0, 1.3),
        w("اسٹاک", 1.4, 1.8),
        w("ختم", 1.9, 2.1),
        w("ہو", 2.2, 2.3),
        w("جاتا", 2.4, 2.6),
        w("ہے۔", 2.7, 3.0),
        w("کیوں؟", 3.1, 3.5),
        w("कब", 3.6, 3.8),
        w("होगा।", 3.9, 4.2),
    ]
    lines = [t for t, _, _ in sentences(words)]
    assert lines == ["Hello there.", "ہمارا اسٹاک ختم ہو جاتا ہے۔", "کیوں؟", "कब होगा।"]
    first = sentences(words)[0]
    assert first[1] == 0 and first[2] == 0.9


def test_a_long_pause_ends_a_line_even_without_a_full_stop():
    words = [w("stock", 0, 0.4), w("runs", 0.5, 0.8), w("out", 0.9 + GAP_S + 1, 3.0)]
    assert [t for t, _, _ in sentences(words)] == ["stock runs", "out"]


def test_a_run_without_punctuation_is_cut_before_it_grows_without_end():
    words = [w("word" * 5, i * 0.2, i * 0.2 + 0.1) for i in range(60)]
    lines = sentences(words)
    assert len(lines) > 1 and all(len(t) <= MAX_LINE_CHARS + 25 for t, _, _ in lines)
    assert sum(len(t.split()) for t, _, _ in lines) == 60  # nothing lost


def test_no_words_no_lines():
    assert sentences([]) == []


def test_the_providers_file_name_says_who_spoke():
    for user in (STAFF, GUEST):
        name = f"individual_pi_room_{CALL}_{user}_{UUID}_audio_only_1795529489096.mkv"
        found = rp._RECORDING_NAME.match(name)
        assert found and found.group("user") == user
    for bad in (
        f"individual_pi_room_{CALL}_probe_a_{UUID}_audio_only_1.mkv",  # not one of our user ids
        f"individual_other_{CALL}_{STAFF}_{UUID}_audio_only_1.mkv",  # another call type
        f"composite_pi_room_{CALL}.mp4",
        "",
    ):
        assert rp._RECORDING_NAME.match(bad) is None, bad


def test_captions_are_asked_for_in_a_language_the_provider_knows():
    assert rp.caption_language("en") == "en" and rp.caption_language("hi") == "hi"
    assert rp.caption_language("ur") == "auto"  # the provider has no Urdu
    assert rp.caption_language("") == "auto" and rp.caption_language("xx") == "auto"


def test_the_providers_times_are_read_with_long_fractions_and_bad_ones_are_dropped():
    assert rp._when("2026-11-24T14:11:30.381123456Z").year == 2026
    assert rp._when("nonsense") is None and rp._when(None) is None


def test_the_timed_words_of_a_reply_are_read_safely():
    data = {
        "words": [
            {"word": " آج ", "start": 0.5, "end": 0.9},
            {"word": "", "start": 1, "end": 2},
            {"word": "bad", "start": "x", "end": 2},
            {"word": "back", "start": 5, "end": 4},  # an end before the start is not trusted
            "junk",
            {"word": True, "start": 1, "end": 2},
        ]
    }
    assert _words(data) == [Word("آج", 0.5, 0.9), Word("back", 5.0, 5.0)]
    assert _words({}) == [] and _words({"words": "nope"}) == []


def _provider(handler):
    return rp.StreamProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)), "k", "s")


def test_the_recordings_listed_by_the_provider_are_only_ours_and_only_from_its_cdn():
    good = f"individual_pi_room_{CALL}_{STAFF}_{UUID}_audio_only_1.mkv"
    other = f"individual_pi_room_{CALL}_{GUEST}_{UUID}_audio_only_2.mkv"

    def handler(request):
        assert request.url.path.endswith(f"/video/call/pi_room/{CALL}/recordings")
        return httpx.Response(
            200,
            json={
                "recordings": [
                    {"filename": good, "url": CDN, "start_time": "2026-11-24T14:11:30.381Z"},
                    {"filename": other, "url": "https://evil.example.com/x.mkv"},
                    {"filename": "composite_x.mp4", "url": CDN},
                    "junk",
                ]
            },
        )

    found = asyncio.run(_provider(handler).recordings(CALL))
    assert [(r.user_id, r.url) for r in found] == [(STAFF, CDN)]
    assert found[0].start is not None


def test_a_recording_is_downloaded_only_from_the_cdn_and_only_if_it_fits():
    big = b"x" * (rp.MAX_AUDIO_BYTES + 1)
    answers = {"small": httpx.Response(200, content=b"ok"), "big": httpx.Response(200, content=big)}

    def handler(request):
        return answers[request.url.params.get("which", "small")]

    provider = _provider(handler)
    assert asyncio.run(provider.download(CDN + "?which=small")) == b"ok"
    assert asyncio.run(provider.download(CDN + "?which=big")) is None
    try:
        asyncio.run(provider.download("https://evil.example.com/x.mkv"))
    except rp.RoomProviderError as error:
        assert error.code == "ROOM_RECORDING_UNTRUSTED"
    else:
        raise AssertionError("an address off the provider's CDN must never be fetched")
