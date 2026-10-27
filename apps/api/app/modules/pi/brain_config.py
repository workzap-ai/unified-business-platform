"""The brain's tunable numbers (pi Brain spec 9.9 and 9.10).

Every default is a starting value chosen by judgement. A workspace may change one under
`response_rules.brain` (for example {"summary_trigger": 5}); a value outside its tested range is
clamped, so a typo can never reach one of the fixed rules. Numbers that belong to a constitutional
rule (one question per message, no pitching, disclosure) are deliberately not here.
"""

from typing import Any

# key: (default, lowest tested value, highest tested value)
TUNABLES: dict[str, tuple[int, int, int]] = {
    # Platform spec v1.4, 17.2: wait for a quiet window of 6 s before replying to a burst (it was
    # lowered 10 -> 5 on 2026-10-24 for latency; 6 s is the spec's own number, the floor stays 5).
    "debounce_seconds": (6, 5, 20),
    # ... but never keep a burst waiting longer than this after its first message (17.2).
    "burst_max_seconds": (25, 15, 60),
    "max_clarify": (3, 1, 3),
    "summary_trigger": (7, 5, 10),
    "quiet_before_summary": (2, 1, 3),  # "anything else?" replies with nothing new, then a summary
    "word_cap": (60, 42, 78),  # a normal message, +-30% (spec 9.10)
    "summary_word_cap": (160, 112, 208),  # the sorted summary
    "document_word_cap": (120, 84, 156),  # a message that carries a link
    "followup_silence_hours": (20, 4, 23),
    "paused_followup_days": (3, 2, 7),
    "document_followup_first_days": (2, 1, 3),
    "document_followup_second_days": (7, 5, 10),
    "redisclose_days": (30, 14, 60),
    "canary_percent": (10, 5, 50),  # share of conversations that see a new example first
    "canary_min_days": (3, 2, 14),  # at least this long before a canary can be promoted
    "canary_min_uses": (30, 20, 300),  # replies that used it before it can be promoted
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


# The least confidence (percent) at which pi suggests that two problems share a root. It starts at
# the default and moves per industry from what staff confirm and reject (`learning_links`).
LINK_DEFAULT = 60
LINK_RANGE = (50, 85)


def link_pct(response_rules: dict[str, Any] | None, industry: str | None) -> int:
    brain = (response_rules or {}).get("brain") or {}
    raw = (brain.get("link_thresholds") or {}).get(
        industry or "_other"
    )  # "_other": no industry yet
    if raw is None:
        raw = brain.get("link_threshold_pct")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return LINK_DEFAULT
    return max(LINK_RANGE[0], min(LINK_RANGE[1], int(raw)))
