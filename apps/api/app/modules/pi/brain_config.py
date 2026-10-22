"""The brain's tunable numbers (pi Brain spec 9.9 and 9.10).

Every default is a starting value chosen by judgement. A workspace may change one under
`response_rules.brain` (for example {"summary_trigger": 5}); a value outside its tested range is
clamped, so a typo can never reach one of the fixed rules. Numbers that belong to a constitutional
rule (one question per message, no pitching, disclosure) are deliberately not here.
"""

from typing import Any

# key: (default, lowest tested value, highest tested value)
TUNABLES: dict[str, tuple[int, int, int]] = {
    "debounce_seconds": (10, 5, 20),
    "max_clarify": (3, 1, 3),
    "summary_trigger": (7, 5, 10),
    "followup_silence_hours": (20, 4, 23),
    "paused_followup_days": (3, 2, 7),
    "document_followup_first_days": (2, 1, 3),
    "document_followup_second_days": (7, 5, 10),
    "redisclose_days": (30, 14, 60),
}


def value(response_rules: dict[str, Any] | None, key: str) -> int:
    """The setting for `key`: the workspace's own value clamped to its range, else the default."""
    default, low, high = TUNABLES[key]
    raw = ((response_rules or {}).get("brain") or {}).get(key)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return default
    return max(low, min(high, int(raw)))


def describe(response_rules: dict[str, Any] | None) -> dict[str, dict[str, int]]:
    """Every setting with its current value and range, for an admin screen or a log line."""
    return {
        key: {"value": value(response_rules, key), "default": d, "low": lo, "high": hi}
        for key, (d, lo, hi) in TUNABLES.items()
    }
