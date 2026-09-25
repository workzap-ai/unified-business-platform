"""SigV4 against AWS's published vectors.

* aws-sig-v4-test-suite: get-vanilla, get-vanilla-query-order-key-case, post-vanilla
  (credentials AKIDEXAMPLE / wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY, 20150830T123600Z,
  region us-east-1, service "service").
* Amazon S3 API reference, "Signature Calculations for the Authorization Header":
  GET Object example and the presigned-URL example (AKIAIOSFODNN7EXAMPLE,
  20130524T000000Z, bucket examplebucket, key test.txt).
"""

from datetime import UTC, datetime

import pytest

from app.integrations.sigv4 import presign_url, sign_headers

SUITE = {
    "access_key": "AKIDEXAMPLE",
    "secret_key": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
    "region": "us-east-1",
    "service": "service",
    "now": datetime(2015, 8, 30, 12, 36, tzinfo=UTC),
}
S3 = {
    "access_key": "AKIAIOSFODNN7EXAMPLE",
    "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "region": "us-east-1",
    "now": datetime(2013, 5, 24, tzinfo=UTC),
}


@pytest.mark.parametrize(
    "method,url,signature",
    [
        (
            "GET",
            "https://example.amazonaws.com/",
            "5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31",
        ),
        (
            "GET",
            "https://example.amazonaws.com/?Param2=value2&Param1=value1",
            "b97d918cfa904a5beff61c982a1b6f458b799221646efd99d3219ec94cdf2500",
        ),
        (
            "POST",
            "https://example.amazonaws.com/",
            "5da7c1a2acd57cee7505fc6676e4e544621c30862966e37dddb68e92efbe5d6b",
        ),
    ],
)
def test_aws_sigv4_suite(method, url, signature):
    headers = sign_headers(method, url, {"host": "example.amazonaws.com"}, **SUITE)
    assert headers["authorization"] == (
        "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
        f"SignedHeaders=host;x-amz-date, Signature={signature}"
    )
    assert headers["x-amz-date"] == "20150830T123600Z"


def test_s3_get_object_example():
    headers = sign_headers(
        "GET",
        "https://examplebucket.s3.amazonaws.com/test.txt",
        {"host": "examplebucket.s3.amazonaws.com", "range": "bytes=0-9"},
        service="s3",
        **S3,
    )
    assert headers["x-amz-content-sha256"] == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assert headers["authorization"].endswith(
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    )


def test_s3_presigned_url_example():
    url = presign_url("GET", "https://examplebucket.s3.amazonaws.com/test.txt", expires=86400, **S3)
    assert url.endswith(
        "X-Amz-Signature=aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404"
    )
    assert "X-Amz-Credential=AKIAIOSFODNN7EXAMPLE%2F20130524%2Fus-east-1%2Fs3%2Faws4_request" in url
    with pytest.raises(ValueError):
        presign_url("GET", "https://b.s3.amazonaws.com/k", expires=604801, **S3)
