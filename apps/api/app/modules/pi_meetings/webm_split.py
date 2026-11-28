"""Cut a long Matroska/WebM recording into pieces a speech-to-text service will take (pure python).

The speech services take at most about 25 MB in one file. A long call, or a high bitrate, goes over,
and the person's lines then fell back to the provider's captions, which have no Urdu. This splits
the file at cluster boundaries (a cluster is a few seconds of audio that decodes by itself), so each
piece is a small valid WebM of its own: the stream header (info and tracks), then whole clusters.

* No new dependency and no ffmpeg: it reads the EBML structure directly.
* Each piece starts its clock at zero (every cluster's timecode is rewritten), and `split` says how
  many milliseconds into the recording each piece begins, so the caller puts the words back.
* It never invents audio and never drops a cluster. A file it cannot read gives None, and the
  caller treats it as it always did (the provider's lines stay).
* It cuts between clusters, so a word that straddles a cut can be heard in two halves. That costs a
  syllable at the edge, not a missing minute.

Nothing is stored: bytes in, bytes out.
"""

from dataclasses import dataclass

EBML_HEADER = 0x1A45DFA3
SEGMENT = 0x18538067
CLUSTER = 0x1F43B675
INFO = 0x1549A966
TRACKS = 0x1654AE6B
TIMECODE = 0xE7
TIMESCALE = 0x2AD7B1
# top-level elements: an unknown-size cluster ends where one of these begins
LEVEL1 = {
    CLUSTER,
    INFO,
    TRACKS,
    0x114D9B74,  # seek head
    0x1C53BB6B,  # cues
    0x1254C367,  # tags
    0x1043A770,  # chapters
    0x1941A469,  # attachments
}
UNKNOWN = -1
DEFAULT_SCALE_NS = 1_000_000  # one tick is one millisecond unless the file says otherwise
UNKNOWN_SIZE = b"\x01\xff\xff\xff\xff\xff\xff\xff"


class NotWebm(ValueError):
    """The bytes are not a Matroska file this module can cut."""


def _id(data: bytes, pos: int) -> tuple[int, int]:
    """(element id, length of the id in bytes); the length marker stays in the id."""
    if pos >= len(data):
        raise NotWebm("end")
    first = data[pos]
    length = 1
    mask = 0x80
    while length <= 4 and not first & mask:
        length += 1
        mask >>= 1
    if length > 4 or pos + length > len(data):
        raise NotWebm("id")
    return int.from_bytes(data[pos : pos + length], "big"), length


def _size(data: bytes, pos: int) -> tuple[int, int]:
    """(size, length of the size field); UNKNOWN for the all-ones live-stream size."""
    if pos >= len(data):
        raise NotWebm("end")
    first = data[pos]
    length = 1
    mask = 0x80
    while length <= 8 and not first & mask:
        length += 1
        mask >>= 1
    if length > 8 or pos + length > len(data):
        raise NotWebm("size")
    value = first & (mask - 1)
    for byte in data[pos + 1 : pos + length]:
        value = (value << 8) | byte
    if value == (1 << (7 * length)) - 1:
        return UNKNOWN, length
    return value, length


def _uint(data: bytes) -> int:
    return int.from_bytes(data, "big") if data else 0


def _children(data: bytes, start: int, end: int) -> list[tuple[int, int, int, int]]:
    """(id, element start, payload start, payload end) of the elements between start and end."""
    out = []
    pos = start
    while pos < end:
        ident, id_len = _id(data, pos)
        size, size_len = _size(data, pos + id_len)
        body = pos + id_len + size_len
        stop = end if size == UNKNOWN else min(end, body + size)
        out.append((ident, pos, body, stop))
        pos = stop
    return out


def _unknown_cluster_end(data: bytes, body: int, end: int) -> int:
    """Where a live-stream cluster of unknown size stops: at the next top-level element."""
    pos = body
    while pos < end:
        ident, id_len = _id(data, pos)
        if ident in LEVEL1:
            return pos
        size, size_len = _size(data, pos + id_len)
        if size == UNKNOWN:
            raise NotWebm("child")
        pos += id_len + size_len + size
    return end


@dataclass(frozen=True)
class Piece:
    start_ms: int  # how far into the recording this piece begins
    data: bytes


def _timecode_element(value: int) -> bytes:
    return bytes([TIMECODE, 0x88]) + value.to_bytes(8, "big")


def _size_field(size: int) -> bytes:
    return bytes([0x01]) + size.to_bytes(7, "big")


def _parse(data: bytes) -> tuple[bytes, int, list[tuple[int, int, int]]]:
    """(header bytes to keep, tick in ns, [(cluster start, cluster end, timecode)])."""
    ident, id_len = _id(data, 0)
    if ident != EBML_HEADER:
        raise NotWebm("not matroska")
    size, size_len = _size(data, id_len)
    if size == UNKNOWN:
        raise NotWebm("header")
    ebml_end = id_len + size_len + size
    ident, id_len = _id(data, ebml_end)
    if ident != SEGMENT:
        raise NotWebm("no segment")
    size, size_len = _size(data, ebml_end + id_len)
    body = ebml_end + id_len + size_len
    seg_end = len(data) if size == UNKNOWN else min(len(data), body + size)

    keep = bytearray()
    scale = DEFAULT_SCALE_NS
    clusters: list[tuple[int, int, int]] = []
    pos = body
    while pos < seg_end:
        ident, id_len = _id(data, pos)
        size, size_len = _size(data, pos + id_len)
        payload = pos + id_len + size_len
        if ident == CLUSTER:
            stop = (
                _unknown_cluster_end(data, payload, seg_end) if size == UNKNOWN else payload + size
            )
            stop = min(stop, seg_end)
            timecode = 0
            for child, _start, c_body, c_end in _children(data, payload, stop):
                if child == TIMECODE:
                    timecode = _uint(data[c_body:c_end])
                    break
            clusters.append((pos, stop, timecode))
        else:
            stop = seg_end if size == UNKNOWN else min(seg_end, payload + size)
            if ident in (INFO, TRACKS):  # the seek head and cues point at offsets that will change
                keep += data[pos:stop]
            if ident == INFO:
                for child, _start, c_body, c_end in _children(data, payload, stop):
                    if child == TIMESCALE:
                        scale = _uint(data[c_body:c_end]) or DEFAULT_SCALE_NS
        pos = stop
    if not clusters:
        raise NotWebm("no audio")
    header = bytes(data[:ebml_end]) + SEGMENT.to_bytes(4, "big") + UNKNOWN_SIZE + bytes(keep)
    return header, scale, clusters


def _rebased(data: bytes, cluster: tuple[int, int, int], zero: int) -> bytes:
    """One cluster with its own timecode moved so that the piece starts at zero."""
    start, stop, timecode = cluster
    ident, id_len = _id(data, start)
    size, size_len = _size(data, start + id_len)
    payload = start + id_len + size_len
    rest_from = payload
    for child, _c_start, _c_body, c_end in _children(data, payload, stop):
        if child == TIMECODE:
            rest_from = c_end
            break
    rest = data[rest_from:stop]
    body = _timecode_element(max(0, timecode - zero)) + rest
    return CLUSTER.to_bytes(4, "big") + _size_field(len(body)) + body


def split(data: bytes, max_bytes: int) -> list[Piece]:
    """Pieces of at most about `max_bytes` each, in order. One piece (the file itself) when it
    already fits. Raises NotWebm when the structure cannot be read."""
    if len(data) <= max_bytes:
        return [Piece(0, data)]
    header, scale, clusters = _parse(data)
    budget = max_bytes - len(header)
    if budget <= 0:
        raise NotWebm("header too large")
    pieces: list[Piece] = []
    group: list[tuple[int, int, int]] = []
    used = 0

    def flush() -> None:
        if not group:
            return
        zero = group[0][2]
        body = b"".join(_rebased(data, c, zero) for c in group)
        start_ms = round((zero - clusters[0][2]) * scale / 1_000_000)
        pieces.append(Piece(max(0, start_ms), header + body))

    for cluster in clusters:
        size = cluster[1] - cluster[0] + 8  # a rebased cluster can carry a wider size field
        if group and used + size > budget:
            flush()
            group, used = [], 0
        group.append(cluster)
        used += size
    flush()
    return pieces
