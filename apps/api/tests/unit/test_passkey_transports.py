"""Sign-in asks for this device's lock (or a phone nearby), never a USB security key."""

from webauthn import generate_authentication_options

from app.modules.auth.passkeys import descriptor, request_options_json


def test_saved_transports_are_sent_back():
    key = descriptor("AAAA", "internal,hybrid,bogus")
    assert [t.value for t in key.transports or []] == ["internal", "hybrid"]


def test_keys_without_saved_transports_mean_this_device_or_a_phone():
    key = descriptor("AAAA")
    assert [t.value for t in key.transports or []] == ["internal", "hybrid"]


def test_sign_in_options_carry_transports_and_hints():
    options = generate_authentication_options(
        rp_id="example.test", allow_credentials=[descriptor("AAAA", "")]
    )
    result = request_options_json(options)
    assert result["hints"] == ["client-device", "hybrid"]
    assert result["allowCredentials"][0]["transports"] == ["internal", "hybrid"]
