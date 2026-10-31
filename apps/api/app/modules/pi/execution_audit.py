# ruff: noqa: E501
"""Controlled execution (Q-8): append-only, hash-chained audit trail. Pure and dry-run: no database,
no I/O, no clock reads (the caller passes `at`). Design: docs/pi-saas/pi-controlled-execution-design.md.

Every decision, action, refusal, verification and rollback is one entry. Each entry's hash covers its
own fields and the previous entry's hash, so editing, removing from the middle, reordering or inserting
an entry is detected by `verify_chain`. Dropping entries from the END is only detectable when the caller
kept the head hash (`expected_head`); that is a stated limit of any chain without an external anchor.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

GENESIS = "0" * 64
MAX_DETAIL = 500
MAX_FIELD = 120
MAX_ENTRIES = 100_000

KINDS = frozenset(
    {
        "decision",
        "approval",
        "action",
        "refusal",
        "verification",
        "rollback",
        "transition",
        "scope",
    }
)

_CARD = re.compile(r"\d(?:[ -]?\d){12,18}")
_EMAIL = re.compile(r"[^\s@]{1,64}@[^\s@]{1,255}")


def _clean(value: Any, limit: int) -> str:
    """Bounded, redacted text: card-like digit runs and emails never enter the trail."""
    text = value if isinstance(value, str) else str(value)
    text = text[: limit * 4]
    text = _CARD.sub("[number]", text)
    text = _EMAIL.sub("[email]", text)
    return text[:limit]


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    at: str
    kind: str
    actor: str
    task_id: str
    detail: str
    prev_hash: str
    hash: str


def _digest(seq: int, at: str, kind: str, actor: str, task_id: str, detail: str, prev: str) -> str:
    body = json.dumps(
        [seq, at, kind, actor, task_id, detail, prev], ensure_ascii=True, separators=(",", ":")
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChainVerdict:
    ok: bool
    bad_index: int | None = None
    reason: str = ""


class AuditLog:
    """Append-only. There is no update or delete method; `entries` is an immutable tuple."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    @property
    def entries(self) -> tuple[AuditEntry, ...]:
        return tuple(self._entries)

    @property
    def head(self) -> str:
        return self._entries[-1].hash if self._entries else GENESIS

    def append(
        self, *, at: datetime, kind: str, actor: str, task_id: str, detail: str = ""
    ) -> AuditEntry | None:
        """Returns the entry, or None when the input is malformed or the log is full (fail closed)."""
        if kind not in KINDS or not isinstance(at, datetime) or at.tzinfo is None:
            return None
        if len(self._entries) >= MAX_ENTRIES:
            return None
        seq = len(self._entries)
        at_s = at.isoformat()
        actor_s = _clean(actor, MAX_FIELD)
        task_s = _clean(task_id, MAX_FIELD)
        detail_s = _clean(detail, MAX_DETAIL)
        prev = self.head
        entry = AuditEntry(
            seq,
            at_s,
            kind,
            actor_s,
            task_s,
            detail_s,
            prev,
            _digest(seq, at_s, kind, actor_s, task_s, detail_s, prev),
        )
        self._entries.append(entry)
        return entry


def verify_chain(entries: Any, expected_head: str | None = None) -> ChainVerdict:
    """Linear time. Never raises; anything malformed is a failed verdict."""
    try:
        items = list(entries)
        prev = GENESIS
        for i, e in enumerate(items):
            if not isinstance(e, AuditEntry):
                return ChainVerdict(False, i, "not an audit entry")
            if e.seq != i:
                return ChainVerdict(
                    False, i, "sequence broken (entry removed, inserted or reordered)"
                )
            if e.kind not in KINDS:
                return ChainVerdict(False, i, "unknown kind")
            if e.prev_hash != prev:
                return ChainVerdict(False, i, "previous hash does not match")
            if e.hash != _digest(e.seq, e.at, e.kind, e.actor, e.task_id, e.detail, e.prev_hash):
                return ChainVerdict(False, i, "entry content does not match its hash")
            prev = e.hash
        if expected_head is not None and expected_head != prev:
            return ChainVerdict(
                False,
                len(items),
                "head differs from the anchor (entries dropped or added at the end)",
            )
        return ChainVerdict(True)
    except Exception:  # noqa: BLE001 - fail closed
        return ChainVerdict(False, None, "unreadable chain")
