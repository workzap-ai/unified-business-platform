"""The two gates (server environment, workspace setting) and the tunables of the bridge."""

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

DEFAULT_TIMEOUT = 2.5
DEFAULT_BREAKER_FAILURES = 5
DEFAULT_BREAKER_COOLDOWN = 30.0
DEFAULT_SEND_PER_MINUTE = 60
MAX_TEXT_CHARS = 1000

_BOOLS = ("enabled", "send_enabled", "capture", "board")
_NUMBERS: dict[str, tuple[float, float]] = {
    "timeout_seconds": (0.5, 5.0),
    "breaker_failures": (2, 20),
    "breaker_cooldown_seconds": (5, 600),
    "send_per_minute": (1, 600),
}
_KEYS = {*_BOOLS, *_NUMBERS}


def validate_workspace_section(value: Any) -> bool:
    """True when `response_rules.nori_bridge` is well formed (used by the settings validator)."""
    if not isinstance(value, dict) or not set(value) <= _KEYS:
        return False
    for key in _BOOLS:
        if key in value and type(value[key]) is not bool:
            return False
    for key, (low, high) in _NUMBERS.items():
        if key in value:
            item = value[key]
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                return False
            if not low <= item <= high:
                return False
    return True


@dataclass(frozen=True)
class BridgeEnv:
    """What the server provides. Built only when both variables are present."""

    base_url: str
    secret: str

    @property
    def host(self) -> str:
        return (urlparse(self.base_url).hostname or "").lower()

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"


def _clean_base(raw: str) -> str | None:
    value = (raw or "").strip().rstrip("/")
    parsed = urlparse(value)
    if not parsed.hostname or parsed.path not in ("", "/"):
        return None
    local = parsed.hostname in {"localhost", "127.0.0.1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def read_env(settings: Any) -> BridgeEnv | None:
    """The bridge's environment, or None (inert) when either variable is missing or unusable."""
    secret = getattr(settings, "workzap_bridge_secret", None)
    value = secret.get_secret_value() if secret is not None else ""
    base = _clean_base(getattr(settings, "nori_base_url", "") or "")
    if base is None or len(value) < 16:
        return None
    return BridgeEnv(base_url=base, secret=value)


def killed(settings: Any) -> bool:
    return getattr(settings, "nori_bridge_kill", False) is True


@dataclass(frozen=True)
class WorkspaceBridge:
    timeout: float = DEFAULT_TIMEOUT
    breaker_failures: int = DEFAULT_BREAKER_FAILURES
    breaker_cooldown: float = DEFAULT_BREAKER_COOLDOWN
    send_enabled: bool = True
    send_per_minute: int = DEFAULT_SEND_PER_MINUTE
    capture: bool = False
    # The Nori Platform board (pi_saas/nori_board): numbers added on the board are filed by pi
    # itself, and nori may push items through POST /api/pi/nori-board.
    board: bool = False


def workspace_bridge(response_rules: dict[str, Any] | None) -> WorkspaceBridge | None:
    """The workspace's settings, or None unless `enabled` is exactly true."""
    raw = (response_rules or {}).get("nori_bridge")
    if not isinstance(raw, dict) or raw.get("enabled") is not True:
        return None
    if not validate_workspace_section(raw):
        return None  # a malformed section never half-enables the bridge

    def number(key: str, default: float) -> float:
        low, high = _NUMBERS[key]
        item = raw.get(key, default)
        return max(low, min(high, float(item)))

    return WorkspaceBridge(
        timeout=number("timeout_seconds", DEFAULT_TIMEOUT),
        breaker_failures=int(number("breaker_failures", DEFAULT_BREAKER_FAILURES)),
        breaker_cooldown=number("breaker_cooldown_seconds", DEFAULT_BREAKER_COOLDOWN),
        send_enabled=raw.get("send_enabled", True) is True,
        send_per_minute=int(number("send_per_minute", DEFAULT_SEND_PER_MINUTE)),
        capture=raw.get("capture", False) is True,
        board=raw.get("board", False) is True,
    )
