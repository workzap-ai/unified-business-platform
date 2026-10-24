"""The rule index (rule_index.json) is a permanent proof of how much of the two specification
PDFs pi has: every rule the PDFs define, what it requires, the code that enforces it and the
tests that exercise it. This file keeps the proof honest. It fails when

* a code file, function or test named in the index is removed or renamed,
* a rule id the PDFs define is missing from the index (the id list is embedded in the index, so no
  PDF is needed),
* a status contradicts its evidence (DONE without a test, a gap with nothing said, ...),
* docs/pi-saas/pi-rule-coverage.md stops matching the index.

Run it with `-s` to see the summary. When a guard changes, change the index in the same commit.
"""

import ast
import json
from collections import Counter
from functools import cache
from pathlib import Path

import pytest

API = Path(__file__).resolve().parents[2]
REPO = API.parents[1]
INDEX = json.loads((Path(__file__).with_name("rule_index.json")).read_text(encoding="utf-8"))
RULES: list[dict] = INDEX["rules"]
STATUSES = set(INDEX["statuses"])
DOC = REPO / "docs" / "pi-saas" / "pi-rule-coverage.md"


@cache
def names_in(path: str) -> frozenset[str]:
    """Every function, class and assigned name defined anywhere in a Python file."""
    tree = ast.parse((API / path).read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
        elif isinstance(node, ast.Assign):
            found.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(node.target, ast.Name):
            found.add(node.target.id)
    return frozenset(found)


def check_reference(ref: str, kind: str) -> None:
    path, _, name = ref.partition("::")
    assert (API / path).is_file(), f"{kind} file is missing: {path}"
    if path.endswith(".py") and name:
        assert name in names_in(path), f"{kind} {path} no longer defines {name}"
    if kind == "test" and path.endswith(".py"):
        assert name.startswith("test"), f"{ref} is not a test"


def test_the_index_has_the_expected_shape():
    assert INDEX["version"] == 1
    assert RULES, "the index is empty"
    ids = [r["id"] for r in RULES]
    assert len(ids) == len(set(ids)), [k for k, v in Counter(ids).items() if v > 1]
    for r in RULES:
        assert set(r) >= {"id", "source", "page", "statement", "status", "code", "tests", "gap"}, r[
            "id"
        ]
        assert r["status"] in STATUSES, f"{r['id']}: unknown status {r['status']}"
        assert r["source"] in ("brain", "addendum2"), r["id"]
        assert 1 <= r["page"] <= 467 and r["statement"].strip(), r["id"]


def test_every_rule_id_the_pdfs_define_is_in_the_index():
    ids = {r["id"] for r in RULES}
    pdf_ids = set(INDEX["pdf_rule_ids"])
    assert len(pdf_ids) >= 150, "the embedded PDF id list was lost"
    assert all(i.startswith("R-") for i in pdf_ids)
    assert not pdf_ids - ids, f"rules the PDFs define but the index lacks: {sorted(pdf_ids - ids)}"
    # the identifier families of the tables and test lists are present too
    for family, count in (
        ("RT", 29),
        ("G", 15),
        ("L", 14),
        ("E", 9),
        ("M", 10),
        ("A", 8),
        ("X", 5),
        ("SL-", 10),
        ("VAL-", 6),
        ("P", 26),
    ):
        expected = {f"{family}{n}" for n in range(1, count + 1)}
        assert expected <= ids, f"{family}: {sorted(expected - ids)}"
    assert {f"Job {n}" for n in range(1, 11)} <= ids and {f"Job S{n}" for n in range(1, 9)} <= ids
    assert {f"RUB-{n}" for n in range(1, 21)} <= ids and {f"App.D-{n}" for n in range(1, 14)} <= ids


@pytest.mark.parametrize("rule", RULES, ids=[r["id"] for r in RULES])
def test_every_file_function_and_test_the_rule_names_still_exists(rule):
    for ref in rule["code"]:
        check_reference(ref, "code")
    for ref in rule["tests"]:
        check_reference(ref, "test")


@pytest.mark.parametrize("rule", RULES, ids=[r["id"] for r in RULES])
def test_the_status_matches_its_evidence(rule):
    status, gap = rule["status"], rule["gap"].strip()
    has_unit = any(t.startswith("tests/unit/") for t in rule["tests"])
    assert rule["unit_tested"] == has_unit, f"{rule['id']}: unit_tested is stale"
    if status == "DONE":
        assert rule["code"] or rule["id"].startswith("App."), f"{rule['id']}: DONE with no code"
        assert rule["tests"], f"{rule['id']}: DONE with no test"
        assert not gap, f"{rule['id']}: DONE rules carry no gap, use PARTIAL"
    elif status == "PARTIAL":
        assert rule["code"] and gap, f"{rule['id']}: PARTIAL needs code and the gap"
    elif status == "CODE-ONLY":
        assert rule["code"] and not has_unit, f"{rule['id']}: CODE-ONLY has no code or has a test"
    elif status == "PROMPT-ONLY":
        assert gap, f"{rule['id']}: say what is not checked"
    elif status == "HUMAN":
        assert gap and rule.get("owner"), f"{rule['id']}: say what is needed and from whom"
    elif status == "MISSING":
        assert gap and not rule["code"], (
            f"{rule['id']}: MISSING says what is missing and has no code"
        )
    if status != "DONE":
        assert rule.get("owner"), f"{rule['id']}: an open rule says who should close it"


def counts() -> dict[str, dict[str, int]]:
    out: dict[str, Counter] = {"brain": Counter(), "addendum2": Counter(), "all": Counter()}
    for r in RULES:
        out[r["source"]][r["status"]] += 1
        out["all"][r["status"]] += 1
    return {k: dict(v) for k, v in out.items()}


def test_the_summary(capsys):
    table = counts()
    only_integration = [r["id"] for r in RULES if r["status"] == "DONE" and not r["unit_tested"]]
    with capsys.disabled():
        print("\nrule index summary")
        for source in ("brain", "addendum2", "all"):
            total = sum(table[source].values())
            parts = ", ".join(f"{s} {table[source].get(s, 0)}" for s in INDEX["statuses"])
            print(f"  {source:10} {total:4} rules: {parts}")
        print(f"  DONE but tested only by integration tests: {len(only_integration)}")
    assert sum(table["all"].values()) == len(RULES)


def test_the_coverage_document_matches_the_index():
    text = DOC.read_text(encoding="utf-8")
    table = counts()
    line = "index counts: " + ", ".join(f"{s} {table['all'].get(s, 0)}" for s in INDEX["statuses"])
    assert line in text, f"docs/pi-saas/pi-rule-coverage.md must contain exactly: {line}"
    for r in RULES:
        if r["status"] != "DONE":
            assert f"`{r['id']}`" in text, (
                f"{r['id']} ({r['status']}) is missing from the coverage document"
            )
    done = {r["id"] for r in RULES if r["status"] == "DONE"}
    for row in text.splitlines():
        cell = row.split("|")[1].strip() if row.startswith("| `") else ""
        if cell.startswith("`") and cell.endswith("`"):
            assert cell.strip("`") not in done, f"{cell} is DONE in the index but listed as open"
