"""S3-compatible object storage (Amazon S3, Cloudflare R2, MinIO) with our SigV4 signer.

Test connection: HEAD bucket (read-only). Objects: PUT / GET / DELETE / HEAD, and
presigned GET/PUT URLs. Keys are validated (no traversal, bounded length) and always
placed under the connection's key prefix; platform callers add a tenant/environment
prefix via `scoped_key`.
"""

import hashlib
import re
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlsplit

from app.core.config import Settings
from app.integrations.errors import IntegrationError
from app.integrations.http import OutboundResponse
from app.integrations.providers.base import credential, ok, require_field
from app.integrations.registry import (
    ConfigField,
    ConfigurationInvalid,
    HealthResult,
    IntegrationDefinition,
    ObjectMetadata,
    ProviderContext,
    StorageProvider,
)
from app.integrations.sigv4 import presign_url, sign_headers

BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
REGION = re.compile(r"^[a-z0-9-]{2,32}$")
KEY_CHARS = re.compile(r"^[A-Za-z0-9!_.*'()/ -]+$")

DEFINITION = IntegrationDefinition(
    key="s3",
    name="S3-compatible storage",
    description="Store files in Amazon S3, Cloudflare R2, MinIO or another S3-compatible service.",
    category="storage",
    provider="S3-compatible",
    auth_type="api_key",
    capabilities=("upload", "download", "delete", "exists", "signed_url", "metadata"),
    documentation_url="https://docs.aws.amazon.com/AmazonS3/latest/API/Welcome.html",
    config_schema=(
        ConfigField(
            "endpoint_url",
            "Endpoint URL",
            "url",
            help="e.g. https://s3.us-east-1.amazonaws.com or your R2/MinIO endpoint",
        ),
        ConfigField("bucket", "Bucket", "text"),
        ConfigField("region", "Region", "text", help="Use 'auto' for Cloudflare R2"),
        ConfigField(
            "addressing",
            "Addressing style",
            "select",
            required=False,
            options=(("path", "Path style"), ("virtual", "Virtual-hosted")),
        ),
        ConfigField("key_prefix", "Key prefix", "text", required=False),
        ConfigField("access_key_id", "Access key ID", "password", secret=True),
        ConfigField("secret_access_key", "Secret access key", "password", secret=True),
    ),
)


def scoped_key(tenant_id: object, environment_id: object, key: str) -> str:
    """Tenant/environment isolation inside a shared bucket."""
    return f"t/{tenant_id}/e/{environment_id}/{key.lstrip('/')}"


def _validate_key(key: str) -> str:
    if not key or len(key) > 900 or key.startswith("/") or not KEY_CHARS.fullmatch(key):
        raise IntegrationError("INVALID_KEY", "The object key is invalid")
    if any(part in ("", ".", "..") for part in key.split("/")):
        raise IntegrationError("INVALID_KEY", "The object key is invalid")
    return key


class S3Provider(StorageProvider):
    key = "s3"
    capabilities = frozenset(DEFINITION.capabilities)

    def validate_configuration(
        self, config: Mapping[str, Any], credentials: Mapping[str, str], settings: Settings
    ) -> None:
        endpoint = require_field(config, "endpoint_url", "Endpoint URL")
        parts = urlsplit(endpoint)
        if (
            parts.scheme not in ("https", "http")
            or not parts.hostname
            or parts.path not in ("", "/")
            or parts.query
            or parts.username
        ):
            raise ConfigurationInvalid("Enter the service endpoint without a path", "endpoint_url")
        if not BUCKET.fullmatch(require_field(config, "bucket", "Bucket")):
            raise ConfigurationInvalid("Bucket name is invalid", "bucket")
        region = str(config.get("region") or settings.storage_default_region)
        if not REGION.fullmatch(region):
            raise ConfigurationInvalid("Region is invalid", "region")
        if config.get("addressing", "path") not in ("path", "virtual"):
            raise ConfigurationInvalid("Choose an addressing style", "addressing")
        prefix = str(config.get("key_prefix") or "")
        if prefix:
            _validate_key(prefix.rstrip("/") + "/x")

    def _region(self, ctx: ProviderContext) -> str:
        return str(ctx.config.get("region") or ctx.settings.storage_default_region)

    def _url(self, ctx: ProviderContext, key: str | None) -> str:
        endpoint = str(ctx.config["endpoint_url"]).rstrip("/")
        bucket = str(ctx.config["bucket"])
        path = ""
        if key is not None:
            prefix = str(ctx.config.get("key_prefix") or "").strip("/")
            full = _validate_key(f"{prefix}/{key}" if prefix else key)
            path = "/" + quote(full, safe="/-_.~")
        if ctx.config.get("addressing") == "virtual":
            parts = urlsplit(endpoint)
            return f"{parts.scheme}://{bucket}.{parts.netloc}{path or '/'}"
        return f"{endpoint}/{bucket}{path}"

    async def _call(
        self,
        ctx: ProviderContext,
        method: str,
        key: str | None,
        body: bytes = b"",
        extra: Mapping[str, str] | None = None,
        max_bytes: int | None = None,
    ) -> OutboundResponse:
        url = self._url(ctx, key)
        headers = sign_headers(
            method,
            url,
            dict(extra or {}),
            access_key=credential(ctx.credentials, "access_key_id"),
            secret_key=credential(ctx.credentials, "secret_access_key"),
            region=self._region(ctx),
            service="s3",
            payload_hash=hashlib.sha256(body).hexdigest(),
        )
        headers.pop("host", None)  # httpx sets Host from the URL (identical value)
        return await ctx.http.request(
            method,
            url,
            headers=headers,
            content=body if body else None,
            max_bytes=max_bytes or 64 * 1024,
            context=ctx.call,
        )

    async def health_check(self, ctx: ProviderContext) -> HealthResult:
        started = time.perf_counter()
        response = await self._call(ctx, "HEAD", None)
        if response.status_code == 404:
            raise IntegrationError("BUCKET_NOT_FOUND", "The bucket does not exist", status=404)
        response.ensure_success()
        return ok(
            "Bucket reachable with these credentials", int((time.perf_counter() - started) * 1000)
        )

    def _meta(
        self, key: str, response: OutboundResponse, size: int | None = None
    ) -> ObjectMetadata:
        length = response.headers.get("content-length", "0")
        return ObjectMetadata(
            key=key,
            size=size if size is not None else int(length) if length.isdigit() else 0,
            content_type=response.headers.get("content-type"),
            etag=(response.headers.get("etag") or "").strip('"') or None,
            last_modified=response.headers.get("last-modified"),
        )

    async def upload(
        self, ctx: ProviderContext, key: str, content: bytes, content_type: str
    ) -> ObjectMetadata:
        if len(content) > ctx.settings.storage_max_upload_bytes:
            raise IntegrationError("OBJECT_TOO_LARGE", "The file is too large")
        response = await self._call(ctx, "PUT", key, content, {"content-type": content_type[:100]})
        response.ensure_success()
        return self._meta(key, response, len(content))

    async def download(self, ctx: ProviderContext, key: str) -> bytes:
        response = await self._call(
            ctx, "GET", key, max_bytes=ctx.settings.storage_max_upload_bytes
        )
        if response.status_code == 404:
            raise IntegrationError("OBJECT_NOT_FOUND", "The file does not exist", status=404)
        response.ensure_success()
        return response.content

    async def delete(self, ctx: ProviderContext, key: str) -> None:
        response = await self._call(ctx, "DELETE", key)
        if response.status_code != 404:
            response.ensure_success()

    async def exists(self, ctx: ProviderContext, key: str) -> bool:
        response = await self._call(ctx, "HEAD", key)
        if response.status_code == 404:
            return False
        response.ensure_success()
        return True

    async def metadata(self, ctx: ProviderContext, key: str) -> ObjectMetadata:
        response = await self._call(ctx, "HEAD", key)
        if response.status_code == 404:
            raise IntegrationError("OBJECT_NOT_FOUND", "The file does not exist", status=404)
        response.ensure_success()
        return self._meta(key, response)

    def signed_url(
        self, ctx: ProviderContext, key: str, expires_seconds: int, method: str = "GET"
    ) -> str:
        if method not in ("GET", "PUT"):
            raise IntegrationError("UNSUPPORTED_OPERATION", "Only GET/PUT URLs can be signed")
        return presign_url(
            method,
            self._url(ctx, key),
            access_key=credential(ctx.credentials, "access_key_id"),
            secret_key=credential(ctx.credentials, "secret_access_key"),
            region=self._region(ctx),
            expires=min(expires_seconds, ctx.settings.storage_signed_url_ttl_seconds),
            now=datetime.now(UTC),
        )
