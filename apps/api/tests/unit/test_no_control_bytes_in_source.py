"""Guard: no stray control byte in any Python source in the repository.

A literal backspace (0x08) where a regex word boundary was meant made patterns that never match
(map_edit.STRONG_LINK, three idea_filter asset patterns). Tab, newline and carriage return are the
only C0 bytes allowed. The scan covers every .py file in the repo (apps, scripts, tests), not only
apps/api.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
ALLOWED = {9, 10, 13}
SKIP_DIRS = {".venv", "venv", "node_modules", "__pycache__", ".git", ".cache", "site-packages"}


def _sources() -> list[Path]:
    return [
        p
        for p in REPO_ROOT.rglob("*.py")
        if not SKIP_DIRS.intersection(p.relative_to(REPO_ROOT).parts)
    ]


def _hits(data: bytes) -> list[tuple[int, int]]:
    out = []
    for number, line in enumerate(data.split(b"\n"), start=1):
        out.extend((number, c) for c in set(line) if c < 32 and c not in ALLOWED)
    return out


def test_the_scan_finds_the_source_tree() -> None:
    names = {p.relative_to(REPO_ROOT).parts[:2] for p in _sources()}
    assert len(_sources()) > 50
    assert ("apps", "api") in names


def test_no_python_source_holds_a_control_byte() -> None:
    found = [
        f"{p.relative_to(REPO_ROOT)}:{line} byte 0x{byte:02x}"
        for p in _sources()
        for line, byte in _hits(p.read_bytes())
    ]
    assert not found, (
        "control bytes in source (a backspace is a mistyped regex boundary):\n" + "\n".join(found)
    )


def test_the_scan_would_catch_a_backspace() -> None:
    bad = b"x = 1\nr = " + bytes([8]) + b"word" + bytes([8]) + b"\n"
    assert _hits(bad) == [(2, 8)]
    assert _hits(b"a\tb\r\nc\n") == []
