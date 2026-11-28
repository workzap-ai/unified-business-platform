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


def test_a_gzipped_callback_is_signed_over_the_unzipped_bytes_and_cannot_balloon():
    import gzip

    body = b'{"type":"call.session_ended","call_cid":"pi_room:rabc"}'
    zipped = gzip.compress(body)
    assert rp.plain_body(body, 1000) == body
    assert rp.plain_body(zipped, 1000) == body
    sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert rp.verify_signature(SECRET, sig, rp.plain_body(zipped, 1000) or b"")
    assert not rp.verify_signature(
        SECRET, sig, zipped
    )  # the signature is not over the zipped bytes
    assert rp.plain_body(b"\x1f\x8bnot gzip at all", 1000) is None
    bomb = gzip.compress(b"0" * 100_000)
    assert len(bomb) < 1000 and rp.plain_body(bomb, 1000) is None
    assert rp.plain_body(b"x" * 2000, 1000) is None


def test_a_room_user_may_react_and_an_older_call_type_is_brought_up_to_date():
    assert "create-reaction" in rp.USER_GRANTS  # a raised hand and emoji reactions
    assert not {"end-call", "mute-users", "block-users"} & set(rp.USER_GRANTS)
    old = {"grants": {"user": ["join-call", "read-call"], "admin": list(rp.USER_GRANTS)}}
    assert rp.missing_grants(old)
    assert rp.missing_grants({})
    assert not rp.missing_grants({"grants": {"user": rp.USER_GRANTS, "admin": rp.USER_GRANTS}})


async def test_ensure_call_type_adds_the_missing_grant_once_and_leaves_a_current_type_alone():
    import httpx

    seen: list[tuple[str, str, dict]] = []
    state = {"grants": {"user": ["join-call", "read-call", "send-audio"], "admin": ["join-call"]}}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        seen.append((request.method, request.url.path, body))
        if request.method == "GET":
            return httpx.Response(
                200,
                json={**state, "settings": {"individual_recording": rp.INDIVIDUAL_AUDIO}},
            )
        state["grants"] = body.get("grants", state["grants"])
        return httpx.Response(200, json={})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = rp.StreamProvider(http, "key", SECRET)
    await provider.ensure_call_type()
    puts = [s for s in seen if s[0] == "PUT"]
    assert len(puts) == 1 and puts[0][2]["grants"]["user"] == rp.USER_GRANTS
    assert "settings" not in puts[0][2]  # only what was missing
    await provider.ensure_call_type()  # now current: no second write
    assert len([s for s in seen if s[0] == "PUT"]) == 1
