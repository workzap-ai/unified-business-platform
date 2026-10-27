"""The daily drift run: fixtures only, no database, no model."""

import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.modules.pi import drift_check as dc
from app.modules.pi import policy
from app.modules.pi_saas import drift_run

PACK = {
    "name": "Tailor Shop",
    "kind": "industry",
    "signals": ["stitching", "fabric", "suit", "measurement", "eid", "delivery"],
}
SOLUTION = {
    "version": "1.1",
    "problems": [
        {
            "workzap_build": {"text": "We keep a record of every order."},
            "quick_ideas": ["Write the order in a book."],
            "extra_ideas": [{"text": "Call before delivery."}],
        }
    ],
    "sample_reply": {"pi": "That helps. What is the first thing that goes wrong?"},
}


def detect_for(key: str, hits: int = 3):
    calls = {"n": 0}

    def detect(_text: str) -> Any:
        calls["n"] += 1
        return SimpleNamespace(primary=key if calls["n"] <= hits else "other")

    return detect


def row(solution=SOLUTION, hits=3, pack=PACK):
    return dc.industry_row(
        "tailor",
        pack,
        solution,
        detect=detect_for("tailor", hits),
        section=lambda _found: "Industry: Tailor Shop",
    )


def report_of(*rows: dict[str, Any], **summary: Any) -> dict[str, Any]:
    base = {
        "industries": len(rows),
        "pack_stored": len(rows),
        "solution_stored": len(rows),
        "retrieved_2of3": len(rows),
        "prompt_block_missing": 0,
        "tool_word_lines": sum(r["tool_word_lines"] for r in rows),
        "automatic_lines": sum(r["automatic_lines"] for r in rows),
        "ending_repeat": 0,
        "s8_tool_word_strings": 0,
        "s8_automatic_strings": 0,
        "conflict_hits": 0,
    }
    return {
        "summary": {**base, **summary},
        "versions": {"prompt": "p1", "build": "b", "handbook": "h1", "supersession": "s1"},
        "weak": [r["industry_id"] for r in rows if r["retrieved_on_probe"] == "no"],
        "conflicts": [],
        "rows": list(rows),
    }


def test_clean_row():
    r = row()
    assert r["pack_stored"] == r["solution_stored"] == "yes"
    assert r["retrieved_on_probe"] == "yes" and r["final_prompt_contains"] == "yes"
    assert r["tool_word_lines"] == 0 and r["ending_repeat"] == "no"


def test_tool_words_and_automatic_endings_are_counted():
    dirty = {
        "problems": [
            {
                "workzap_build": {"text": "A dashboard shows orders."},
                "quick_ideas": ["It sends reminders automatically.", "Plain idea."],
            }
        ]
    }
    r = row(dirty)
    assert r["tool_word_lines"] == 1 and r["automatic_lines"] == 1 and r["ending_repeat"] == "yes"


def test_probes_never_empty_with_few_signals():
    assert len(dc.probes_for({"signals": ["tea"]})) == 3
    assert dc.probes_for({}) == []


def test_missing_pack_and_weak_probe_are_gaps():
    missing = dc.industry_row("x", None, None, detect=lambda _t: SimpleNamespace(primary=None))
    codes = {f.code for f in dc.gaps(report_of(missing))}
    assert {"missing_pack", "missing_solution", "probe_weak"} <= codes


def test_step8_counts_every_string():
    files = {"a": {"x": ["a system", {"y": "automatically done"}]}, "b": {"z": "fine"}}
    s = dc.step8_counts(files)
    assert (s["tool_word_strings"], s["tool_word_files"]) == (1, 1)
    assert (s["automatic_strings"], s["automatic_files"], s["strings"]) == (1, 1, 3)


def test_fingerprint_round_trip_and_bucket_size():
    rows = [
        {**row(), "industry_id": f"industry_number_{i}", "solution_hash": str(i)}
        for i in range(211)
    ]
    buckets = dc.encode_fingerprints(dc.fingerprints(rows))
    assert all(len(text) <= 300 for text in buckets.values())
    assert len(buckets) <= 40
    assert dc.decode_fingerprints(buckets) == dc.fingerprints(rows)


def test_no_baseline_reports_gaps_only():
    assert dc.compare(None, report_of(row())) == []


def drift_codes(before, after):
    prev = dc.baseline_of(before)
    return {f.code for f in dc.compare(prev, after) if f.kind == "drift"}


def test_no_change_no_drift():
    assert drift_codes(report_of(row()), report_of(row())) == set()


def test_new_tool_word_line_and_automatic_ending_are_drift():
    dirty = {"problems": [{"quick_ideas": ["Use the dashboard automatically."]}]}
    codes = drift_codes(report_of(row()), report_of(row(dirty)))
    assert {"tool_word_lines", "automatic_endings", "version_changed"} <= codes


def test_missing_industry_and_version_and_prompt_change():
    before = report_of(row())
    after = report_of()
    assert "missing_pack" in drift_codes(before, after)
    after2 = report_of(row())
    after2["versions"]["prompt"] = "p2"
    assert "prompt_version" in drift_codes(before, after2)


def test_probe_regression_is_drift():
    assert "probe_regressed" in drift_codes(report_of(row()), report_of(row(hits=0)))


def test_conflict_scan_counts_new_listen_only_lines():
    with tempfile.TemporaryDirectory() as folder:
        _scan(Path(folder))


def _scan(tmp_path: Path) -> None:
    (tmp_path / "brain_prompt.py").write_text(
        '# do not suggest solutions (comment, ignored)\nX = "Never suggest anything yet"\n',
        encoding="utf-8",
    )
    assert dc.conflict_scan(tmp_path, ("brain_prompt.py", "missing.py")) == ["brain_prompt.py:2"]


def test_stamp_summary_flags_unstamped_and_stale():
    summary = dc.stamp_summary(
        [
            {"prompt_version": "old", "pack_versions": {}},
            {"prompt_version": "", "pack_versions": {}},
        ],
        {"prompt": "new"},
    )
    assert summary == {"replies": 2, "stamped": 1, "current_prompt": 0, "with_build": 0}
    assert {f.code for f in dc.stamp_findings(summary)} == {"unstamped_replies", "stale_prompt"}


def test_setting_default_off_and_validated():
    assert drift_run.enabled(None) is False
    assert drift_run.enabled({"brain": {"drift_check": True}}) is True
    assert drift_run.enabled({"brain": {"drift_check": "yes"}}) is False
    source = open(policy.__file__, encoding="utf-8").read()
    assert 'brain.get("drift_check", False)) is bool' in source


@pytest.mark.parametrize("key", ["accounting_audit_and_tax_practices"])
def test_real_industry_passes(key):
    report = dc.build_report(only=(key,))
    assert (
        report["summary"]["pack_stored"] == 1 and report["rows"][0]["retrieved_on_probe"] == "yes"
    )
