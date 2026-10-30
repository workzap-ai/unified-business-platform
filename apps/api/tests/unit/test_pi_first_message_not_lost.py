# ruff: noqa: E501  (long Roman Urdu and comment lines)
"""R3 (audit 2026-10-30): message A is being answered, message B arrives 60 s later. A's draft is
sent (burst older than the cap) or A is dropped; either way A must still be addressed.

Found: after the stale check, step 6 of runtime.process re-checks
`last_inbound_at != inbound_snapshot` and marks A "skipped" WITHOUT an error code. burst_before() only collects BURST_CODES and the
history only reads processed/queued/sent/delivered/read, so B's regenerated reply never sees A."""

import asyncio
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.modules.pi import runtime


def _step6_block() -> str:
    src = open(runtime.__file__, encoding="utf-8").read()
    start = src.index("conversation.last_inbound_at != inbound_snapshot")
    return src[start : start + 900]


def test_a_skipped_at_recheck_is_kept_for_the_burst_answer() -> None:
    block = _step6_block()
    skipped = re.search(r'message\.status, message\.error_code.*?"skipped"', block, re.S)
    sets_code = "error_code" in block.split("return")[0]
    assert sets_code and "BURST_COALESCED" in block, (
        "A is skipped at the step-6 re-check with no BURST code: B's reply will not address A"
    )
    assert skipped or "BURST_COALESCED" in block


class _Session:
    def __init__(self, values):
        self.values = list(values)

    async def scalar(self, _q):
        return self.values.pop(0)


def test_a_old_draft_is_not_dropped_by_the_stale_check() -> None:
    now = datetime.now(UTC)
    a = SimpleNamespace(tenant_id=1, environment_id=1, conversation_id=1, id="A", created_at=now)
    session = _Session(["B", None, now - timedelta(seconds=60)])
    assert asyncio.run(runtime.stale_reply(session, a, {})) is False
