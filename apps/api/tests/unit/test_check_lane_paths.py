"""The lane guard (scripts/check_lane_paths.py): a foreign file fails, own files pass."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_lane_paths.py"
spec = importlib.util.spec_from_file_location("check_lane_paths", SCRIPT)
assert spec and spec.loader
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

PI = "apps/api/app/modules/pi/"


def test_own_files_pass_for_every_lane():
    own = {
        "u": [PI + "problems.py", PI + "slot_carry.py", "apps/api/alembic/versions/0053_x.py"],
        "s": [PI + "system_ask.py", PI + "box_signals.py", PI + "solution_x.py", PI + "part19.py"],
        "e": [PI + "evalkit/scorers.py", PI + "evalkit/cases/a.json", "docs/pi-saas/pi-eval-x.md"],
        "r": ["apps/api/tests/unit/test_x.py", PI + "brain_erase.py"],
        "i": [PI + "industry_packs.py", PI + "packs/industry/dairy.json"],
        "p": ["docs/pi-saas/capability-map.md"],
    }
    for lane, paths in own.items():
        assert guard.foreign_paths(lane, paths) == [], lane
        assert guard.main([lane, *paths]) == 0


def test_a_foreign_file_fails_and_is_listed(capsys):
    paths = [PI + "problems.py", PI + "service_conversation.py"]
    assert guard.foreign_paths("u", paths) == [PI + "service_conversation.py"]
    assert guard.main(["u", *paths]) == 1
    assert "service_conversation.py" in capsys.readouterr().err


def test_lanes_do_not_cross():
    assert guard.foreign_paths("s", [PI + "problems.py"]) != []
    assert guard.foreign_paths("i", [PI + "box.py"]) != []
    assert guard.foreign_paths("e", ["apps/api/tests/unit/test_other.py"]) != []
    assert guard.foreign_paths("r", [PI + "problems.py"]) != []


def test_paths_relative_to_api_and_backslashes_work():
    assert guard.foreign_paths("r", ["tests\\unit\\test_x.py"]) == []
    assert guard.foreign_paths("u", ["app/modules/pi/problems.py"]) == []


def test_traversal_is_foreign():
    assert guard.foreign_paths("r", ["tests/../app/modules/pi/service_conversation.py"]) != []


def test_empty_stage_passes(monkeypatch):
    monkeypatch.setattr(guard, "staged_paths", lambda: [])
    assert guard.main(["u"]) == 0


def test_default_input_is_the_stage(monkeypatch):
    monkeypatch.setattr(guard, "staged_paths", lambda: [PI + "service_conversation.py"])
    assert guard.main(["u"]) == 1
    monkeypatch.setattr(guard, "staged_paths", lambda: [PI + "problems.py"])
    assert guard.main(["u"]) == 0


@pytest.mark.parametrize("argv", [[], ["x"], ["x", "tests/a.py"]])
def test_unknown_lane_or_no_lane_is_an_error(argv, capsys):
    assert guard.main(argv) == 2
    assert capsys.readouterr().err
