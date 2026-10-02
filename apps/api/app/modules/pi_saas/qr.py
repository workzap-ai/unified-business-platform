"""Server-side QR code generation for the pay-by-link flow.

The QR always encodes the pay-page URL itself (never raw bank/wallet details), so
scanning it opens the current, up-to-date instructions and proof form rather than a
possibly stale copied value. No external service or credentials are involved.
"""

import io

import qrcode


def png(url: str) -> bytes:
    """Render ``url`` as a PNG QR code. Raises ``ValueError`` for anything that is not
    an http(s) URL, so a QR can never be generated for an unexpected target."""
    if not url.startswith(("https://", "http://")):
        raise ValueError("QR target must be an http(s) URL")
    image = qrcode.make(url)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
