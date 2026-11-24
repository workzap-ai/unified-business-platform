"""The video room provider's own rules: the callback signature, the token's claims, and which
transcript addresses may ever be fetched."""

import base64
import hashlib
import hmac
import json
from uuid import UUID

from app.modules.pi_meetings import room_provider as rp

SECRET = "unit-test-secret"


def _claims(token: str) -> dict:
    body = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))


def test_a_callback_is_ours_only_with_the_exact_signature():
    body = b'{"type":"call.session_ended"}'
    good = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert rp.verify_signature(SECRET, good, body)
    assert rp.verify_signature(SECRET, good.upper(), body)
    assert not rp.verify_signature(SECRET, good, body + b" ")
    assert not rp.verify_signature(SECRET, "0" * 64, body)
    assert not rp.verify_signature("", good, body)
    assert not rp.verify_signature(SECRET, "", body)


def test_a_user_token_names_one_user_one_call_and_runs_out():
    provider = rp.StreamProvider(None, "key", SECRET)  # type: ignore[arg-type]
    user = rp.guest_user(UUID(int=7))
    claims = _claims(provider.user_token(user, "rabc", ttl_s=600))
    assert claims["user_id"] == user and user.startswith("g_")
    assert claims["call_cids"] == [f"{rp.CALL_TYPE}:rabc"]
    assert 0 < claims["exp"] - claims["iat"] <= 700
    assert "server" not in claims  # a browser token never carries server power


def test_a_token_is_signed_with_the_secret_and_nothing_else():
    token = rp.sign_jwt(SECRET, {"user_id": "s_1"})
    head, body, mac = token.split(".")
    good = hmac.new(SECRET.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
    assert mac == base64.urlsafe_b64encode(good).rstrip(b"=").decode()


def test_call_ids_are_random_and_user_ids_say_who_kind():
    assert rp.new_call_id() != rp.new_call_id() and len(rp.new_call_id()) >= 33
    assert rp.staff_user(UUID(int=1)).startswith("s_")
    assert rp.guest_user(UUID(int=1)).startswith("g_")


def test_only_the_providers_own_cdn_over_https_is_ever_fetched():
    ok = "https://us-east.stream-io-cdn.com/1/video/transcription/t.jsonl"
    assert rp.trusted_transcript_url(ok)
    for bad in (
        "http://us-east.stream-io-cdn.com/t.jsonl",
        "https://evil.example.com/t.jsonl",
        "https://stream-io-cdn.com.evil.example/t.jsonl",
        "https://user:pw@us-east.stream-io-cdn.com/t.jsonl",
        "https://us-east.stream-io-cdn.com:8443/t.jsonl",
        "https://169.254.169.254/latest/meta-data",
        "file:///etc/passwd",
        "",
    ):
        assert not rp.trusted_transcript_url(bad), bad
