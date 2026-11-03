"""The daily drift run (platform spec Part A.3 steps 2, 4 and 8, the A.8 upload checks, 11.10).

"An audit that runs once will be undone by the next upload": this module repeats the checks
that need no model and no live traffic, and says what changed since the last run.

Read-only and free: it reads the stored packs, solution files and prompt sources from disk and
counts. No model call, no write, no network. Persistence and the cron job live in
`app/modules/pi_saas/drift_run.py`; the script is `scripts/pi_drift_check.py`.

What it covers
- A.3 step 4 and the A.4 table: per industry, pack stored, solution stored, version hash,
  three probe messages through the detection path, whether the pack block survives into the
  prompt section, tool-word lines, lines that end on "automatically".
- A.3 step 8: banned tool words and "automatically" counted over every stored string of
  every solution file (the spec's 413 and 210-of-211 are kept as reference numbers).
- A.3 step 2 (as far as a stamp allows): the prompt is not stored whole, so the per-reply
  stamp (`PiReplyAudit.prompt_version`, `pack_versions`) is checked against what is on disk now
  (`stamp_summary`, fed by the DB layer).
- A.8: (1) diff = which files changed since the last run; (2) conflict scan = old listen-only
  instructions still sitting in prompt sources; (3) probe replay = the 211 industry probes (the
  golden conversations need the model and are not replayed here); (4) version stamp = prompt,
  pack and build versions, and the stamp coverage of the last replies.

Drift = something got worse or changed since the previous run (`compare`). Gaps = the spec's
pass mark is not met right now. A first run has no baseline, so it can only report gaps.
"""

import hashlib
import json
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.modules.pi import industry_packs, learning_audit, solutions, spec_handbook

REPORT_VERSION = 1
SPEC_TOOL_WORD_LINES = 413  # platform spec A.3 step 8: what the source document counted
SPEC_AUTOMATIC_FILES = 210  # ... and the files (of 211) that carried "automatically"
MODULE_DIR = Path(__file__).parent
BUCKET = 14  # entries per stored bucket (the audit log keeps strings to 300 characters)

# Old "listen only" instructions that the Solution Mode value line replaced (audit hypothesis 1).
_LISTEN_ONLY = re.compile(
    r"do not (?:suggest|give|offer) (?:any )?(?:solutions?|ideas?)|never suggest|only listen"
    r"|listen first|no solutions? (?:yet|until)",
    re.IGNORECASE,
)
_SCAN_FILES = (
    "brain_prompt.py",
    "think_prompt.py",
    "solution_context.py",
    "service_conversation.py",
)


@dataclass(frozen=True)
class Finding:
    kind: str  # gap | drift
    code: str
    text: str

    def line(self) -> str:
        return f"{self.kind}:{self.code}: {self.text}"[:290]


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)


def _hash(value: Any, size: int = 6) -> str:
    return hashlib.sha1(json.dumps(value, sort_keys=True).encode()).hexdigest()[:size]


def _tag(key: str) -> str:
    return hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()[:6]


def probes_for(pack: Mapping[str, Any]) -> list[str]:
    """Three first messages an owner might send, from the pack's own signal words (English,
    Roman Urdu, mixed). Fewer signals give shorter probes, never none."""
    sig = [x for x in pack.get("signals", []) if isinstance(x, str)]
    if not sig:
        return []
    return [
        f"I run a business, we deal with {sig[0]} and {sig[1]}"
        if len(sig) > 1
        else f"I run a business: {sig[0]}",
        f"mera karobar hai, hamare yahan {sig[2]} aur {sig[3]} ka kaam hota hai"
        if len(sig) > 3
        else f"mera karobar {sig[0]} ka hai",
        f"Hi, my problem is with {sig[4]}, we are in {sig[5]}"
        if len(sig) > 5
        else f"{sig[-1]} ka masla hai",
    ]


def spoken_lines(solution: Mapping[str, Any] | None) -> list[str]:
    """The lines of a solution entry that pi can say to a person."""
    lines: list[str] = []
    for problem in (solution or {}).get("problems") or []:
        lines.append(str((problem.get("workzap_build") or {}).get("text", "")))
        lines.append(str(problem.get("free_stops") or ""))
        lines.append(str(problem.get("ask_first") or ""))
        lines += [str(x) for x in problem.get("quick_ideas") or []]
        lines += [str(e.get("text", "")) for e in problem.get("extra_ideas") or []]
    sample = ((solution or {}).get("sample_reply") or {}).get("pi")
    if sample:
        lines.append(str(sample))
    return [x for x in lines if x]


def industry_row(
    key: str,
    pack: Mapping[str, Any] | None,
    solution: Mapping[str, Any] | None,
    detect: Callable[[str], Any] | None = None,
    section: Callable[[Any], str] | None = None,
) -> dict[str, Any]:
    """One A.4 row. `detect(text)` returns a Detection (default: the live detection path)."""
    detect = detect or (lambda text: industry_packs.detect([text]))
    section = section or industry_packs.prompt_section
    probes = probes_for(pack or {})
    hits = 0
    in_prompt = "n/a"
    for text in probes:
        found = detect(text)
        if getattr(found, "primary", None) == key:
            hits += 1
            if in_prompt == "n/a" and pack:
                in_prompt = (
                    "yes" if str(pack.get("name", "")).lower() in section(found).lower() else "no"
                )
    lines = spoken_lines(solution)
    tool_lines = sum(1 for s in lines if solutions.TOOL_WORD.search(s))
    auto_lines = sum(1 for s in lines if solutions.AUTOMATIC.search(s))
    stored = bool(solution and solution.get("problems"))
    return {
        "industry_id": key,
        "pack_stored": "yes" if pack else "no",
        "pack_version": _hash(pack, 8) if pack else "",
        "solution_stored": "yes" if stored else "no",
        "solution_version": str((solution or {}).get("version", "")),
        "solution_hash": _hash(solution, 8) if solution else "",
        "probes": len(probes),
        "identified_on_probe": hits,
        "retrieved_on_probe": "yes" if hits >= 2 else "no",
        "final_prompt_contains": in_prompt,
        "tool_word_lines": tool_lines,
        "automatic_lines": auto_lines,
        "ending_repeat": "yes" if auto_lines else "no",
    }


def step8_counts(files: Mapping[str, Any]) -> dict[str, int]:
    """A.3 step 8 over every string of every stored solution file (not only spoken lines)."""
    tool_strings = auto_strings = tool_files = auto_files = total = 0
    for data in files.values():
        strings = list(_strings(data))
        total += len(strings)
        tool = sum(1 for s in strings if solutions.TOOL_WORD.search(s))
        auto = sum(1 for s in strings if solutions.AUTOMATIC.search(s))
        tool_strings += tool
        auto_strings += auto
        tool_files += bool(tool)
        auto_files += bool(auto)
    return {
        "files": len(files),
        "strings": total,
        "tool_word_strings": tool_strings,
        "tool_word_files": tool_files,
        "automatic_strings": auto_strings,
        "automatic_files": auto_files,
    }


def conflict_scan(root: Path = MODULE_DIR, names: tuple[str, ...] = _SCAN_FILES) -> list[str]:
    """A.8 check 2, the cheap automatic part: old listen-only instructions in prompt sources
    (comment lines are skipped) and in the spec handbook text. Each hit is `file:line`."""
    hits: list[str] = []
    for name in names:
        path = root / name
        if not path.exists():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.lstrip().startswith("#") and _LISTEN_ONLY.search(line):
                hits.append(f"{name}:{number}")
    handbook = root / "spec" / "handbook.json"
    if handbook.exists():
        text = handbook.read_text(encoding="utf-8")
        hits += [f"handbook.json#{m.start()}" for m in _LISTEN_ONLY.finditer(text)][:20]
    return hits


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:10] if path.exists() else ""


def build_report(only: tuple[str, ...] | None = None) -> dict[str, Any]:
    """Run every file-based check. `only` limits the industries (tests, quick runs)."""
    packs = {k: v for k, v in industry_packs.load_packs().items() if v.get("kind") == "industry"}
    keys = sorted(set(packs) | set(solutions.industries()))
    if only is not None:
        keys = [k for k in keys if k in only]
    rows = [industry_row(k, packs.get(k), solutions.load(k)) for k in keys]
    raw_files: dict[str, Any] = {}
    for path in sorted(solutions.SOLUTIONS_DIR.glob("*.json")):
        raw_files[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    conflicts = conflict_scan()
    step8 = step8_counts(raw_files)
    weak = [r["industry_id"] for r in rows if r["retrieved_on_probe"] == "no"]
    summary = {
        "industries": len(rows),
        "pack_stored": sum(r["pack_stored"] == "yes" for r in rows),
        "solution_stored": sum(r["solution_stored"] == "yes" for r in rows),
        "retrieved_2of3": len(rows) - len(weak),
        "prompt_block_missing": sum(r["final_prompt_contains"] == "no" for r in rows),
        "tool_word_lines": sum(r["tool_word_lines"] for r in rows),
        "automatic_lines": sum(r["automatic_lines"] for r in rows),
        "ending_repeat": sum(r["ending_repeat"] == "yes" for r in rows),
        **{f"s8_{k}": v for k, v in step8.items()},
        "conflict_hits": len(conflicts),
    }
    versions = {
        "prompt": learning_audit.prompt_version(),
        "build": learning_audit.build_id(),
        "handbook": _digest(spec_handbook.PATH),
        "supersession": _digest(spec_handbook.SUPERSESSION),
        "packs": _hash(
            {r["industry_id"]: [r["pack_version"], r["solution_hash"]] for r in rows}, 10
        ),
    }
    return {
        "report_version": REPORT_VERSION,
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "summary": summary,
        "versions": versions,
        "weak": weak,
        "conflicts": conflicts[:10],
        "rows": rows,
    }


# ---- baseline storage (small strings: the audit log truncates anything over 300 characters) --


def fingerprints(rows: list[dict[str, Any]]) -> dict[str, list[Any]]:
    """tag -> [version hash, tool-word lines, automatic lines, retrieved]. The tag is a short
    hash of the industry id, so a bucket stays small; `names` maps tags back to ids."""
    return {
        _tag(r["industry_id"]): [
            _hash([r["pack_version"], r["solution_hash"]]),
            r["tool_word_lines"],
            r["automatic_lines"],
            1 if r["retrieved_on_probe"] == "yes" else 0,
        ]
        for r in rows
    }


def encode_fingerprints(fp: Mapping[str, list[Any]]) -> dict[str, str]:
    items = [f"{tag}:{v[0]}:{v[1]}:{v[2]}:{v[3]}" for tag, v in sorted(fp.items())]
    return {
        f"b{i // BUCKET:02d}": " ".join(items[i : i + BUCKET]) for i in range(0, len(items), BUCKET)
    }


def decode_fingerprints(buckets: Mapping[str, str] | None) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    for text in (buckets or {}).values():
        for item in str(text).split():
            parts = item.split(":")
            if len(parts) == 5 and all(p.lstrip("-").isdigit() for p in parts[2:]):
                out[parts[0]] = [parts[1], int(parts[2]), int(parts[3]), int(parts[4])]
    return out


def baseline_of(report: Mapping[str, Any], findings: list[Finding] | None = None) -> dict[str, Any]:
    """What is stored per run: summary, versions, flagged lists and the fingerprint buckets."""
    return {
        "summary": dict(report["summary"]),
        "versions": dict(report["versions"]),
        "weak": [str(x) for x in report["weak"][:20]],
        "conflicts": list(report["conflicts"][:10]),
        "fp": encode_fingerprints(fingerprints(report["rows"])),
        "findings": [f.line() for f in (findings or [])[:30]],
    }


def gaps(report: Mapping[str, Any]) -> list[Finding]:
    """The A.4 pass mark, right now, with no baseline needed."""
    s = report["summary"]
    out: list[Finding] = []
    for row in report["rows"]:
        if row["pack_stored"] != "yes":
            out.append(
                Finding("gap", "missing_pack", f"{row['industry_id']}: no industry pack stored")
            )
        if row["solution_stored"] != "yes":
            out.append(
                Finding("gap", "missing_solution", f"{row['industry_id']}: no solution entry")
            )
    if report["weak"]:
        out.append(
            Finding(
                "gap",
                "probe_weak",
                f"{len(report['weak'])} industries found on fewer than 2 of 3 probes: "
                + ", ".join(report["weak"][:5]),
            )
        )
    if s["prompt_block_missing"]:
        out.append(
            Finding(
                "gap",
                "prompt_block",
                f"{s['prompt_block_missing']} packs missing from the prompt block",
            )
        )
    return out


def compare(prev: Mapping[str, Any] | None, report: Mapping[str, Any]) -> list[Finding]:
    """Gaps now, plus drift against the previous run's stored baseline (`baseline_of`)."""
    findings = gaps(report)
    if not prev or not prev.get("summary"):
        return findings
    s, p = report["summary"], prev["summary"]
    names = {_tag(r["industry_id"]): r["industry_id"] for r in report["rows"]}
    old = decode_fingerprints(prev.get("fp"))
    new = fingerprints(report["rows"])

    def who(tags: list[str]) -> str:
        return ", ".join(names.get(t, f"id#{t}") for t in sorted(tags)[:5])

    gone = [t for t in old if t not in new]
    if gone:
        findings.append(
            Finding("drift", "missing_pack", f"{len(gone)} industries disappeared: {who(gone)}")
        )
    changed = [t for t in new if t in old and old[t][0] != new[t][0]]
    if changed:
        findings.append(
            Finding(
                "drift",
                "version_changed",
                f"{len(changed)} pack or solution versions changed: {who(changed)}",
            )
        )
    added = [t for t in new if t not in old]
    if added:
        findings.append(Finding("drift", "added", f"{len(added)} industries added: {who(added)}"))
    tool_up = [t for t in new if t in old and new[t][1] > old[t][1]]
    if tool_up or s["tool_word_lines"] > p.get("tool_word_lines", s["tool_word_lines"]):
        findings.append(
            Finding(
                "drift",
                "tool_word_lines",
                f"tool-word lines {p.get('tool_word_lines')} -> {s['tool_word_lines']}; "
                f"up in: {who(tool_up)}",
            )
        )
    auto_up = [t for t in new if t in old and new[t][2] > old[t][2]]
    if auto_up or s["automatic_lines"] > p.get("automatic_lines", s["automatic_lines"]):
        findings.append(
            Finding(
                "drift",
                "automatic_endings",
                f"'automatically' lines {p.get('automatic_lines')} -> {s['automatic_lines']}; "
                f"up in: {who(auto_up)}",
            )
        )
    lost = [t for t in new if t in old and old[t][3] == 1 and new[t][3] == 0]
    if lost:
        findings.append(
            Finding(
                "drift",
                "probe_regressed",
                f"{len(lost)} industries no longer retrieved: {who(lost)}",
            )
        )
    for key in ("s8_tool_word_strings", "s8_automatic_strings"):
        if s.get(key, 0) > p.get(key, s.get(key, 0)):
            findings.append(
                Finding("drift", key, f"{key} {p.get(key)} -> {s[key]} (stored solution strings)")
            )
    if s["conflict_hits"] > p.get("conflict_hits", s["conflict_hits"]):
        findings.append(
            Finding(
                "drift",
                "conflict_scan",
                f"listen-only instructions {p.get('conflict_hits')} -> {s['conflict_hits']}: "
                + ", ".join(report["conflicts"][:3]),
            )
        )
    for key in ("prompt", "handbook", "supersession"):
        before = (prev.get("versions") or {}).get(key)
        if before and before != report["versions"][key]:
            findings.append(
                Finding("drift", f"{key}_version", f"{key} {before} -> {report['versions'][key]}")
            )
    return findings


def stamp_summary(
    stamps: Sequence[Mapping[str, Any]], current: Mapping[str, Any] | None = None
) -> dict[str, int]:
    """A.3 step 2 and A.8 check 4 for the last replies (rows of prompt_version and pack_versions).
    `current` is the live prompt version and per-pack digests; a stamp that names an older one is
    `stale`, which is normal for a few replies after a deploy and drift when it stays so."""
    live = (current or {}).get("prompt") or learning_audit.prompt_version()
    return {
        "replies": len(stamps),
        "stamped": sum(1 for s in stamps if s.get("prompt_version")),
        "current_prompt": sum(1 for s in stamps if s.get("prompt_version") == live),
        "with_build": sum(1 for s in stamps if (s.get("pack_versions") or {}).get("build")),
    }


def stamp_findings(summary: Mapping[str, int]) -> list[Finding]:
    n = summary["replies"]
    out: list[Finding] = []
    if n and summary["stamped"] < n:
        out.append(
            Finding(
                "drift",
                "unstamped_replies",
                f"{n - summary['stamped']} of the last {n} replies carry no prompt version",
            )
        )
    if n and summary["current_prompt"] == 0 and summary["stamped"]:
        out.append(
            Finding(
                "drift", "stale_prompt", f"none of the last {n} replies used the prompt on disk now"
            )
        )
    return out
