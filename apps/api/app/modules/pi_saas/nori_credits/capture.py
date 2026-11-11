"""Requirements and problems for the Workzap team: pi passes on what a nori member needs or what
does not work in nori (nori's requirements inbox, docs/credits-pi-contract.md section 3b).

This is a LIBRARY. It is deliberately not wired into pi's brain: the brain's state machine and
tool catalogue have no narrow hook for "the owner asked pi to tell the Workzap team", and adding
one would touch rules that are never to be weakened (one question per message, no solution while
listening). The extension point is documented in docs/pi-saas/nori-bridge.md: a caller that has
decided the member explicitly asked (see `explicit_request`) calls `capture_nori_item`.

Every function:
  * checks with `identify` first, number only, and sends nothing about a number nori does not know;
  * never raises, and returns a CaptureResult whose `reply` (when present) is nori's own wording,
    safe to send as it is;
  * stays inside nori's contract: kind in KINDS, https file links, text lengths.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.modules.pi_saas.nori_credits.client import NoriClient
from app.modules.pi_saas.nori_credits.resilience import METRICS

KINDS = ("feature", "problem", "question", "meeting", "change")
SEVERITIES = ("low", "normal", "high", "critical")
FILE_KINDS = ("image", "document", "audio", "video")
MAX_FILES = 10
_ITEM = re.compile(r"R?\d{1,9}", re.IGNORECASE)


@dataclass
class CaptureResult:
    ok: bool
    reason: str = ""
    reply: str | None = None
    ref: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


def _clip(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split()) if limit <= 200 else value.strip()
    return text[:limit] or None


def _files(files: Any) -> list[dict[str, Any]] | None:
    """Valid file links (https only), or None when the list is invalid."""
    if files is None:
        return []
    if not isinstance(files, list) or len(files) > MAX_FILES:
        return None
    clean = []
    for item in files:
        if not isinstance(item, dict):
            return None
        url = item.get("url")
        if item.get("kind") not in FILE_KINDS or not isinstance(url, str):
            return None
        if not url.lower().startswith("https://") or len(url) > 2000:
            return None
        entry: dict[str, Any] = {"kind": item["kind"], "url": url}
        if isinstance(item.get("name"), str):
            entry["name"] = item["name"][:200]
        if isinstance(item.get("size"), int) and item["size"] >= 0:
            entry["size"] = item["size"]
        clean.append(entry)
    return clean


def _result(call: Any) -> CaptureResult:
    data = call.data
    if call.ok and data.get("ok") is not False:
        return CaptureResult(
            True,
            "",
            data.get("reply") if isinstance(data.get("reply"), str) else None,
            data.get("ref") if isinstance(data.get("ref"), str) else None,
            data,
        )
    reason = data.get("reason") if isinstance(data.get("reason"), str) else call.reason
    return CaptureResult(
        False, reason, data.get("reply") if isinstance(data.get("reply"), str) else None, None, data
    )


async def _member(client: NoriClient, sender: str) -> CaptureResult | None:
    """None when the sender is a nori member; otherwise the refusal."""
    identity = await client.identify(sender)
    if not identity.checked:
        return CaptureResult(False, "nori_unreachable")
    if not identity.known:
        return CaptureResult(False, "not_member")
    return None


async def capture_nori_item(
    client: NoriClient,
    sender: str,
    *,
    kind: str,
    title: str,
    description: str | None = None,
    expected: str | None = None,
    what_happened: str | None = None,
    page: str | None = None,
    module: str | None = None,
    severity: str | None = None,
    files: list[dict[str, Any]] | None = None,
    language: str | None = None,
    message_id: str | None = None,
) -> CaptureResult:
    """Record a feature, problem, question, meeting request or change with the Workzap team."""
    kind = (kind or "").strip().lower()
    clean_title = _clip(title, 200)
    if kind not in KINDS:
        return CaptureResult(False, "invalid_kind")
    if clean_title is None or len(clean_title) < 3:
        return CaptureResult(False, "invalid_title")
    if severity is not None and severity not in SEVERITIES:
        return CaptureResult(False, "invalid_severity")
    clean_files = _files(files)
    if clean_files is None:
        return CaptureResult(False, "bad_file")
    refusal = await _member(client, sender)
    if refusal is not None:
        METRICS.inc("capture", refusal.reason)
        return refusal
    call = await client.structured(
        "capture",
        sender,
        kind=kind,
        title=clean_title,
        description=_clip(description, 4000),
        expected=_clip(expected, 2000),
        actual=_clip(what_happened, 2000),
        page=_clip(page, 300),
        module=_clip(module, 80),
        severity=severity,
        language=language if language in {"en", "ur"} else None,
        files=clean_files or None,
        message_id=(message_id or None) and message_id[:100],
    )
    METRICS.inc("capture", "ok" if call.ok else call.reason)
    return _result(call)


def _item(item: str | None) -> str | None:
    value = (item or "").strip()
    return value.upper() if _ITEM.fullmatch(value) else None


async def nori_item_status(
    client: NoriClient, sender: str, item: str | None = None
) -> CaptureResult:
    if item is not None and _item(item) is None:
        return CaptureResult(False, "no_such_item")
    refusal = await _member(client, sender)
    if refusal is not None:
        return refusal
    return _result(await client.structured("item_status", sender, item=_item(item)))


async def nori_item_followups(client: NoriClient, sender: str) -> CaptureResult:
    """Items the Workzap team is waiting on, with the team's question, for pi to relay."""
    refusal = await _member(client, sender)
    if refusal is not None:
        return refusal
    return _result(await client.structured("item_followups", sender))


async def nori_item_reply(client: NoriClient, sender: str, item: str, text: str) -> CaptureResult:
    """The person's answer to the team's question (or more details)."""
    ref, clean = _item(item), _clip(text, 4000)
    if ref is None:
        return CaptureResult(False, "no_such_item")
    if clean is None:
        return CaptureResult(False, "invalid_text")
    refusal = await _member(client, sender)
    if refusal is not None:
        return refusal
    return _result(await client.structured("item_reply", sender, item=ref, text=clean))


_EXPLICIT = re.compile(
    r"\b(?:tell|inform|notify|message|report(?:\s+(?:this|it))?\s+to|pass(?:\s+(?:this|it))?"
    r"\s+(?:on\s+)?to|let)\s+(?:the\s+)?workzap(?:\s+team)?(?:\s+know)?\b",
    re.IGNORECASE,
)


def explicit_request(text: str) -> bool:
    """True only when the person plainly asks pi to tell the Workzap team something ("tell the
    Workzap team the invoice logo is blurry", "let Workzap know ..."). A complaint on its own is
    not a request: pi's brain keeps listening, and nori's own prefixes (Fix:, Question: ...) are
    answered by nori's inbound door."""
    return bool(_EXPLICIT.search(text or ""))
