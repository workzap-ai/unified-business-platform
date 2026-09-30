from typing import Any


def as_dict(value: Any) -> dict[str, Any]:
    """Untrusted JSON: a dict, or an empty one."""
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
