"""A long recording is cut at cluster boundaries into valid pieces that start at zero."""

import pytest

from app.modules.pi_meetings import native_stt, webm_split
from app.modules.pi_meetings.webm_split import NotWebm, split


def vint(size: int) -> bytes:
    return bytes([0x01]) + size.to_bytes(7, "big")


def element(ident: int, body: bytes, unknown: bool = False) -> bytes:
    raw = ident.to_bytes((ident.bit_length() + 7) // 8, "big")
    return raw + (webm_split.UNKNOWN_SIZE if unknown else vint(len(body))) + body


def cluster(timecode: int, blocks: int, unknown: bool = False) -> bytes:
    tc = element(0xE7, timecode.to_bytes(2, "big"))
    audio = b"".join(element(0xA3, bytes([i % 250]) * 100) for i in range(blocks))
    return element(webm_split.CLUSTER, tc + audio, unknown=unknown)


def recording(clusters: int, unknown: bool = False, scale: int | None = None) -> bytes:
    ebml = element(webm_split.EBML_HEADER, element(0x4282, b"webm"))
    info_body = element(0x2AD7B1, scale.to_bytes(4, "big")) if scale else b""
    info = element(webm_split.INFO, info_body + element(0x4489, b"\x00\x01"))
    tracks = element(webm_split.TRACKS, element(0xAE, b"opus"))
    seek = element(0x114D9B74, b"\x00" * 20)
    body = (
        seek
        + info
        + tracks
        + b"".join(cluster(5000 + i * 2000, 5, unknown) for i in range(clusters))
    )
    return ebml + element(webm_split.SEGMENT, body)


def timecodes(piece: bytes) -> list[int]:
    _header, _scale, found = webm_split._parse(piece)
    return [tc for _s, _e, tc in found]


def test_a_file_that_fits_is_one_piece_and_untouched() -> None:
    data = recording(3)
    assert split(data, len(data)) == [webm_split.Piece(0, data)]


@pytest.mark.parametrize("unknown", [False, True])
def test_a_long_file_becomes_valid_pieces_that_keep_every_cluster(unknown: bool) -> None:
    data = recording(12, unknown=unknown)
    pieces = split(data, len(data) // 3)
    assert len(pieces) >= 3
    assert all(len(p.data) <= len(data) // 3 + 16 for p in pieces)
    seen = 0
    for piece in pieces:
        clusters = timecodes(piece.data)
        assert clusters[0] == 0  # every piece starts its own clock at zero
        assert clusters == sorted(clusters)
        seen += len(clusters)
    assert seen == 12  # no cluster is lost or doubled


def test_each_piece_says_how_far_into_the_recording_it_begins() -> None:
    data = recording(12)
    pieces = split(data, len(data) // 3)
    starts = [p.start_ms for p in pieces]
    assert starts[0] == 0 and starts == sorted(starts) and len(set(starts)) == len(starts)
    # clusters are 2000 ticks apart: a piece of n clusters ends where the next one starts
    assert all(s % 2000 == 0 for s in starts)


def test_the_tick_size_in_the_file_is_respected() -> None:
    data = recording(12, scale=2_000_000)  # one tick is two milliseconds
    pieces = split(data, len(data) // 3)
    assert pieces[1].start_ms == (len(timecodes(pieces[0].data)) * 2000) * 2


def test_a_file_that_is_not_matroska_cannot_be_cut() -> None:
    with pytest.raises(NotWebm):
        split(b"x" * 5000, 1000)
    with pytest.raises(NotWebm):
        split(recording(0), 10)


def test_transcription_joins_the_pieces_on_one_clock() -> None:
    import asyncio

    from app.ai.types import Word

    data = recording(12)
    native_stt.CHUNK_BYTES, saved = len(data) // 3, native_stt.CHUNK_BYTES

    class Result:
        def __init__(self, words):
            self.words = words

    class Manager:
        calls = 0

        async def transcribe(self, scope, audio, mime, **kwargs):
            Manager.calls += 1
            return Result([Word("hello", 1.0, 1.5)])

    try:
        words = asyncio.run(native_stt._words(Manager(), None, data, "ur"))
    finally:
        native_stt.CHUNK_BYTES = saved
    pieces = split(data, len(data) // 3)
    assert Manager.calls == len(pieces) and words is not None
    assert [w.start for w in words] == [1.0 + p.start_ms / 1000 for p in pieces]


def test_one_piece_the_service_cannot_read_gives_up_the_whole_file() -> None:
    import asyncio

    from app.ai.errors import GatewayUnavailable

    data = recording(12)
    native_stt.CHUNK_BYTES, saved = len(data) // 3, native_stt.CHUNK_BYTES

    class Manager:
        async def transcribe(self, *args, **kwargs):
            raise GatewayUnavailable("down")

    try:
        assert asyncio.run(native_stt._words(Manager(), None, data, "ur")) is None
    finally:
        native_stt.CHUNK_BYTES = saved
