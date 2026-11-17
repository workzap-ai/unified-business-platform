"""The signed link to a card's photo or file: genuine, expiring, tied to one card."""

from uuid import uuid4

from app.modules.pi_saas.nori_board import media_link

SECRET = "bridge-test-secret-0123456789"


def test_a_token_names_its_card_until_it_expires():
    card = uuid4()
    token = media_link.make_token(SECRET, card, now=1_000)
    assert media_link.read_token(SECRET, token, now=1_500) == card
    assert media_link.read_token(SECRET, token, now=1_000 + media_link.LINK_TTL_SECONDS + 1) is None


def test_a_token_cannot_be_forged_moved_or_extended():
    card, other = uuid4(), uuid4()
    token = media_link.make_token(SECRET, card, now=1_000)
    raw_id, expires, tag = token.split(".")
    assert media_link.read_token("another-secret-0123456789", token, now=1_500) is None
    assert media_link.read_token(SECRET, f"{other.hex}.{expires}.{tag}", now=1_500) is None
    assert (
        media_link.read_token(SECRET, f"{raw_id}.{int(expires) + 99999}.{tag}", now=1_500) is None
    )
    assert media_link.read_token(SECRET, f"{raw_id}.{expires}.{'0' * len(tag)}", now=1_500) is None


def test_garbage_is_refused_without_an_error():
    for junk in ("", "a.b", "a.b.c", "x" * 500, "..", f"{uuid4().hex}.notanumber.abc"):
        assert media_link.read_token(SECRET, junk) is None


def test_no_link_without_a_public_https_address():
    class S:
        integrations_public_base_url = None

    assert media_link.url_for(S(), SECRET, uuid4()) is None
    S.integrations_public_base_url = "http://insecure.test"
    assert media_link.url_for(S(), SECRET, uuid4()) is None
    S.integrations_public_base_url = "https://pi.test/"
    link = media_link.url_for(S(), SECRET, uuid4())
    assert link is not None and link.startswith("https://pi.test/api/pi/nori-media/")
