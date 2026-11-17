"""The meeting-bot provider layer: which links may reach a provider, the provider's status words,
and the signature on its callbacks."""

import base64
import hashlib
import hmac

import pytest

from app.modules.pi_meetings.bot_provider import (
    link_hash,
    our_status,
    parse_meeting_link,
    verify_signature,
)

KEY = b"a-test-secret-of-some-length-0123"
SECRET = "whsec_" + base64.b64encode(KEY).decode()


@pytest.mark.parametrize(
    ("url", "source"),
    [
        ("https://us02web.zoom.us/j/81234567890?pwd=abc", "zoom"),
        ("https://zoom.us/j/81234567890", "zoom"),
        ("https://meet.google.com/abc-defg-hij", "meet"),
        ("https://teams.microsoft.com/l/meetup-join/19%3ameeting_x/0?context=1", "teams"),
        ("https://teams.live.com/meet/9876543210", "teams"),
    ],
)
def test_real_zoom_meet_and_teams_links_are_accepted(url, source):
    found = parse_meeting_link(url)
    assert found is not None and found.source == source


@pytest.mark.parametrize(
    "url",
    [
        "http://zoom.us/j/81234567890",  # not https
        "https://evil.example.com/j/81234567890",  # another site
        "https://zoom.us.evil.example.com/j/81234567890",  # a look-alike host
        "https://user:pass@zoom.us/j/81234567890",  # a login in the address
        "https://zoom.us:8443/j/81234567890",  # a made-up port
        "https://meet.google.com/",  # no meeting code
        "https://meet.google.com/landing",
        "https://zoom.us/",
        "https://169.254.169.254/latest/meta-data",
        "javascript:alert(1)",
        "",
    ],
)
def test_anything_else_never_reaches_a_provider(url):
    assert parse_meeting_link(url) is None


def test_the_same_call_hashes_alike_whatever_the_passcode_or_trailing_slash():
    a = link_hash("https://us02web.zoom.us/j/81234567890?pwd=one")
    b = link_hash("https://us02web.zoom.us/j/81234567890/?pwd=two")
    assert a == b and "81234567890" not in a
    assert a != link_hash("https://us02web.zoom.us/j/81234567891")


def test_the_providers_status_words_map_to_ours():
    assert our_status("bot.in_call_recording") == "recording"
    assert our_status("in_waiting_room") == "waiting"
    assert our_status("bot.fatal") == "failed"
    assert our_status("bot.recording_permission_denied") == "denied"
    assert our_status("bot.breakout_room_opened") is None  # a word we do not track
    assert our_status("brand_new_word") is None


def sign(body: bytes, msg_id="msg_1", stamp="1700000000", key=KEY):
    signed = b".".join([msg_id.encode(), stamp.encode(), body])
    return base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()


def headers(body: bytes, **kw):
    return {
        "webhook-id": "msg_1",
        "webhook-timestamp": "1700000000",
        "webhook-signature": f"v1,{sign(body, **kw)}",
    }


def test_a_correctly_signed_callback_is_accepted():
    body = b'{"event":"bot.done"}'
    assert verify_signature(SECRET, headers(body), body) is True


def test_an_older_secret_in_a_list_of_signatures_still_matches():
    body = b'{"event":"bot.done"}'
    h = headers(body)
    h["webhook-signature"] = (
        f"v1,{sign(body, key=b'another-secret-key-here-0123456')} " + (h["webhook-signature"])
    )
    assert verify_signature(SECRET, h, body) is True


@pytest.mark.parametrize("fault", ["body", "key", "version", "missing", "no-secret", "bad-secret"])
def test_everything_else_is_refused(fault):
    body = b'{"event":"bot.done"}'
    h = headers(body)
    secret = SECRET
    if fault == "body":
        body = b'{"event":"bot.fatal"}'
    elif fault == "key":
        h = headers(body, key=b"not-the-secret-not-the-secret-12")
    elif fault == "version":
        h["webhook-signature"] = h["webhook-signature"].replace("v1,", "v2,")
    elif fault == "missing":
        del h["webhook-id"]
    elif fault == "no-secret":
        secret = ""
    elif fault == "bad-secret":
        secret = "whsec_!!!not base64!!!"
    assert verify_signature(secret, h, body) is False
