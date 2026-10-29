"""Development / Regression / Held-out split.

Regression: every case tagged `regression` (a past failure; never removed, never tuned away).
Held-out: a stable share of the rest chosen by a hash of the case id, so adding cases never moves an
existing case between sets. Held-out cases are not used to tune prompts, extraction or thresholds;
`held_out_access` records who read the results, so any peek is visible.
"""

import hashlib
from typing import Any

HELD_OUT_PERCENT = 25
DEVELOPMENT = "development"
REGRESSION = "regression"
HELD_OUT = "held_out"


def split_of(case: dict[str, Any]) -> str:
    if case.get("regression"):
        return REGRESSION
    digest = hashlib.sha256(str(case["id"]).encode("utf-8")).digest()
    return HELD_OUT if digest[0] % 100 < HELD_OUT_PERCENT else DEVELOPMENT


def held_out_access(log: list[dict[str, str]], who: str, why: str) -> list[dict[str, str]]:
    """The access record to keep next to a held-out result (append-only)."""
    return [*log, {"who": who, "why": why}]
