"""Credential manager: Fernet/MultiFernet encryption of connection credentials at rest.

Keys: `SECRETS_ENCRYPTION_KEY` may hold one key or "new,old,..." (comma-separated); keys
in `SECRETS_ENCRYPTION_PREVIOUS_KEYS` are appended. The first key encrypts; every key can
decrypt. `rotate()` re-encrypts a token with the first key.

Compatibility note: the PI module's legacy helper (app/modules/pi/whatsapp.py) builds a
single `Fernet(SECRETS_ENCRYPTION_KEY)`. Until it delegates here, keep a single key in
SECRETS_ENCRYPTION_KEY and put retired keys in SECRETS_ENCRYPTION_PREVIOUS_KEYS.

Fail closed: without a key, storing or reading credentials raises CredentialsUnavailable
(HTTP 503 ENCRYPTION_NOT_CONFIGURED); nothing is ever stored in plaintext. Only hints
(last four characters) are exposed to the API.
"""

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import Settings
from app.integrations.errors import CredentialsUnavailable, IntegrationError


def _keys(settings: Settings) -> list[str]:
    raw: list[str] = []
    for secret in (settings.secrets_encryption_key, settings.secrets_encryption_previous_keys):
        if secret is not None:
            raw.extend(k.strip() for k in secret.get_secret_value().split(",") if k.strip())
    return raw


def hint(value: str) -> str:
    """Last four characters only, and only when the secret is long enough to spare them."""
    value = str(value)
    return "…" + value[-4:] if len(value) >= 12 else "…"


class CredentialManager:
    def __init__(self, settings: Settings) -> None:
        self._fernet: MultiFernet | None = None
        keys = _keys(settings)
        if keys:
            try:
                self._fernet = MultiFernet([Fernet(k.encode()) for k in keys])
            except (ValueError, TypeError):
                raise IntegrationError(
                    "ENCRYPTION_KEY_INVALID",
                    "SECRETS_ENCRYPTION_KEY is not a valid Fernet key",
                    kind="configuration",
                ) from None

    @property
    def configured(self) -> bool:
        return self._fernet is not None

    def _require(self) -> MultiFernet:
        if self._fernet is None:
            raise CredentialsUnavailable
        return self._fernet

    def encrypt(self, plaintext: str) -> str:
        return self._require().encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._require().decrypt(token.encode()).decode()
        except (InvalidToken, ValueError):
            raise IntegrationError(
                "CREDENTIALS_UNREADABLE",
                "Stored credentials cannot be decrypted; re-enter them",
                kind="configuration",
            ) from None

    def rotate(self, token: str) -> str:
        try:
            return self._require().rotate(token.encode()).decode()
        except (InvalidToken, ValueError):
            raise IntegrationError(
                "CREDENTIALS_UNREADABLE",
                "Stored credentials cannot be decrypted; re-enter them",
                kind="configuration",
            ) from None

    def encrypt_json(self, data: dict[str, Any]) -> str:
        return self.encrypt(json.dumps(data, separators=(",", ":"), sort_keys=True))

    def decrypt_json(self, token: str | None) -> dict[str, Any]:
        if not token:
            return {}
        data = json.loads(self.decrypt(token))
        if not isinstance(data, dict):
            raise IntegrationError(
                "CREDENTIALS_UNREADABLE", "Stored credentials are invalid", kind="configuration"
            )
        return data
