"""Saved recordings: retention, file-type checks and the key layout (no database, no storage)."""

from app.modules.pi_meetings import media
from app.modules.pi_meetings.media_routes import ALLOWED, clean_mime, looks_like

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 16


def test_a_recording_is_kept_a_year_unless_the_workspace_says_otherwise():
    assert media.retention_days(None) == 90
    assert media.retention_days({}) == 90
    assert media.retention_days({"brain": {"meeting_retention_days": 730}}) == 730


def test_retention_stays_inside_its_bounds_and_ignores_nonsense():
    assert (
        media.retention_days({"brain": {"meeting_retention_days": 1}}) == media.MIN_RETENTION_DAYS
    )
    assert (
        media.retention_days({"brain": {"meeting_retention_days": 10**6}})
        == media.MAX_RETENTION_DAYS
    )
    for bad in ("365", 3.5, True, None, [], {}):
        assert media.retention_days({"brain": {"meeting_retention_days": bad}}) == 90


def test_every_allowed_type_has_a_file_extension_and_a_signature_check():
    for mimes in ALLOWED.values():
        for mime in mimes:
            assert mime in media.EXTENSIONS
    assert looks_like("video/webm", WEBM) and looks_like("audio/webm", WEBM)
    assert looks_like("video/mp4", b"\x00\x00\x00\x18ftypisom")
    assert looks_like("audio/ogg", b"OggS\x00") and looks_like("audio/mpeg", b"ID3\x03")
    assert looks_like("audio/wav", b"RIFF\x00\x00\x00\x00WAVEfmt ")


def test_bytes_that_do_not_match_their_type_are_refused():
    assert not looks_like("video/webm", b"<html>not a video</html>")
    assert not looks_like("video/mp4", WEBM)
    assert not looks_like("audio/ogg", WEBM)
    assert not looks_like("application/pdf", b"%PDF-1.7")


def test_the_codec_suffix_is_not_part_of_the_type():
    assert clean_mime("audio/webm;codecs=opus") == "audio/webm"
    assert clean_mime(" Video/WebM ; codecs=vp9,opus") == "video/webm"
    assert clean_mime(None) == ""
