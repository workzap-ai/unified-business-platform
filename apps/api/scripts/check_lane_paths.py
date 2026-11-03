"""Lane guard for the pi Fast-Track plan (section 1): fail when a staged file is outside the lane.

From apps/api (or anywhere in the repo):
    python scripts/check_lane_paths.py u                 # checks `git diff --cached --name-only`
    python scripts/check_lane_paths.py r path1 path2     # checks the paths given
Lanes: u understanding, s solutions, e evaluation, r isolation and release, i industries,
p product audit. Exit 0 when every path is inside the lane (an empty list passes), 1 when any path
is outside (each is listed), 2 for an unknown lane or when git cannot list the stage.

Paths may be repo-root relative (as git prints them, apps/api/...) or relative to apps/api.
A pattern matches the whole path; `*` also crosses folders. Docs and tests outside a lane's own
list are foreign on purpose: add a pattern here (lane R owns this file) rather than
staging across lanes.
"""

import subprocess
import sys
from fnmatch import fnmatchcase

PI = "app/modules/pi/"

LANES: dict[str, tuple[str, ...]] = {
    "u": (
        PI + "problem_models.py",
        PI + "problems.py",
        PI + "problem_extract.py",
        PI + "memory_block.py",
        PI + "slots.py",
        PI + "slot_carry.py",
        PI + "requirements.py",
        "alembic/versions/0053_*",
        "tests/*test_pi_problem*",
        "tests/*test_pi_memory*",
        "tests/*test_pi_slot*",
        "tests/*test_pi_requirements*",
    ),
    "s": (
        PI + "system_ask.py",
        PI + "box*.py",
        PI + "solution_*.py",
        PI + "expert_advisor.py",
        PI + "idea_filter.py",
        PI + "brain_docs*.py",
        PI + "part19.py",
        PI + "brain_visual*.py",
        "tests/*test_pi_box*",
        "tests/*test_pi_solution*",
        "tests/*test_pi_expert*",
        "tests/*test_pi_idea_filter*",
        "tests/*test_pi_brain_doc*",
        "tests/*test_pi_part19*",
        "tests/*test_pi_brain_visual*",
        "tests/*test_pi_artwing*",
        "tests/*test_pi_system_ask*",
    ),
    "e": (
        PI + "evalkit/*",
        "docs/pi-saas/pi-eval*",
        "tests/*test_pi_evalkit*",
    ),
    "r": (
        "tests/*",
        "scripts/check_lane_paths.py",
        PI + "brain_erase.py",
    ),
    "i": (
        PI + "industry_packs.py",
        PI + "industry_words.py",
        PI + "packs/industry/*",
        "scripts/build_industry_packs.py",
        "tests/*test_pi_industr*",
        "tests/*test_pi_pack*",
        "tests/*test_industry*",
    ),
    "p": (
        "docs/pi-saas/capability-map*",
        "tests/*test_pi_capability*",
    ),
}

ROOT_PREFIX = "apps/api/"


def normalise(path: str) -> str:
    text = path.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    if text.startswith(ROOT_PREFIX):
        text = text[len(ROOT_PREFIX) :]
    return text


def foreign_paths(lane: str, paths: list[str]) -> list[str]:
    """The paths outside the lane's allowed patterns, in input order (KeyError for a bad lane)."""
    patterns = LANES[lane.lower()]
    out = []
    for raw in paths:
        if not raw.strip():
            continue
        path = normalise(raw)
        if ".." in path.split("/") or not any(fnmatchcase(path, p) for p in patterns):
            out.append(raw)
    return out


def staged_paths() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff --cached failed")
    return [line for line in result.stdout.splitlines() if line.strip()]


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: check_lane_paths.py <u|s|e|r|i|p> [path ...]", file=sys.stderr)
        return 2
    lane, paths = argv[0].lower(), argv[1:]
    if lane not in LANES:
        print(f"unknown lane {argv[0]!r}; use one of {', '.join(sorted(LANES))}", file=sys.stderr)
        return 2
    if not paths:
        try:
            paths = staged_paths()
        except (RuntimeError, OSError) as exc:
            print(f"cannot list the stage: {exc}", file=sys.stderr)
            return 2
    bad = foreign_paths(lane, paths)
    if bad:
        print(f"lane {lane}: {len(bad)} path(s) outside the lane:", file=sys.stderr)
        for path in bad:
            print(f"  {path}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
