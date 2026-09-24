"""Export registry definitions for the web app's demo adapter.

Run from apps/api:  python -m app.modules.navigation.export
The web app ships this snapshot so demo mode resolves navigation from the same
definitions; live mode always calls GET /api/v1/navigation.
"""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.modules.navigation.definitions import REGISTRY

TARGET = (
    Path(__file__).resolve().parents[4]
    / "web"
    / "src"
    / "features"
    / "navigation"
    / "registry.generated.json"
)


def snapshot() -> list[dict[str, Any]]:
    return [asdict(item) for item in sorted(REGISTRY.definitions(), key=lambda i: i.key)]


def render() -> str:
    return json.dumps(snapshot(), indent=2, sort_keys=True) + "\n"


ACCESS_TARGET = TARGET.parents[1] / "auth" / "access.generated.json"


def access_snapshot() -> dict[str, Any]:
    from app.modules.access.permissions import PERMISSIONS, SYSTEM_ROLES

    return {
        "permissions": [asdict(p) for p in PERMISSIONS.values()],
        "roles": [
            {"key": key, "name": name, "description": description, "permissions": sorted(perms)}
            for key, (name, description, perms) in SYSTEM_ROLES.items()
        ],
    }


def render_access() -> str:
    return json.dumps(access_snapshot(), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    TARGET.write_text(render(), encoding="utf-8")
    ACCESS_TARGET.parent.mkdir(parents=True, exist_ok=True)
    ACCESS_TARGET.write_text(render_access(), encoding="utf-8")
    print(f"Wrote {len(snapshot())} navigation definitions and the access catalog")
