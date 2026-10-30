"""Calibration helpers for the relevance scorer (FT-A3): sample sheets and agreement.

Three label sources are kept strictly apart and never merged into one column:
  scorer         the deterministic scorer (`relevance`)
  agent_drafted  labels an agent drafted from the case design
                 (`relevance_labels_agent_drafted.json`, `human_confirmed: false`)
  human          labels from people reading the human review sheet (a separate file you supply)
The grader agent's verdicts are a fourth, separate input. Agent-drafted labels are NOT human
labels. The 85% acceptance is the owner's decision; this tool only prints numbers.

This module cannot prove who the reviewers are or that they worked independently: two names that
normalise differently might still be one person, and two that match might be two. It checks only
structure (known ids, enough samples, distinct normalised names, no copy of the agent-drafted
labels) and never prints an acceptance verdict. The 85% acceptance is a decision the owner records.

Held-out discipline: every function here that would score or print a Held-out case refuses
(PermissionError) unless it is given an `Access` (log path, who, why), and then writes the log line.

Usage from apps/api:
  python -m app.modules.pi.evalkit.relevance_calibration --sheets OUT_DIR
  python -m app.modules.pi.evalkit.relevance_calibration --grader GRADER.json [--human HUMAN.json]
"""

import argparse
import csv
import json
import random
import unicodedata
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, NamedTuple

from app.modules.pi.evalkit import access_log, relevance, splits

DIR = Path(__file__).with_name("calibration")
CASES = Path(__file__).with_name("cases") / "plan.json"
SAMPLES_PATH = DIR / "relevance_samples.json"
AGENT_PATH = DIR / "relevance_labels_agent_drafted.json"
BORDERLINE_SAMPLES_PATH = DIR / "relevance_samples_borderline.json"
BORDERLINE_AGENT_PATH = DIR / "relevance_labels_agent_drafted_borderline.json"
BLOCKS = ("core", "borderline")
SEED = 20261030
MIN_HUMAN_SAMPLES = 20  # fewest labelled samples before a human agreement number is printed
DEFINITIONS = {
    "relevant": "links to the owner's stated problem, reuses its facts, breaks no stated limit",
    "irrelevant": "specific, but about something the owner did not raise",
    "generic": "would fit almost any business; no link to the stated problem",
    "violates_constraint": "breaks a limit the owner stated",
    "restates_owner": "only repeats what the owner already said, adds nothing",
}
AGENT_COPY_LEVEL = 0.9  # a sheet agreeing with the agent-drafted labels this much is refused
AGENT_COPY_MIN_SAMPLES = 10  # ... once it has at least this many labelled samples
IDENTITY_NOTE = (
    "Identity of reviewers and independence are NOT verified by this tool; the 85% acceptance is "
    "a decision recorded by the owner, not computed here."
)


class Access(NamedTuple):
    """Who reads Held-out cases, why, and where the append-only access log lives."""

    path: str | Path
    who: str
    why: str


def require_access(access: Access | None) -> Access:
    if access is None or not str(access.path).strip():
        raise ValueError("reading Held-out cases needs an access log path")
    if not str(access.who).strip() or not str(access.why).strip():
        raise ValueError("reading Held-out cases needs who and why")
    return access


def guard(cases: list[dict[str, Any]], access: Access | None, what: str) -> int:
    """Refuse (PermissionError) to touch a Held-out case without an access log argument; when one
    is given, write the log line first. Returns how many Held-out cases are involved."""
    held = [c for c in cases if splits.split_of(c) == splits.HELD_OUT]
    if not held:
        return 0
    if access is None:
        raise PermissionError(
            f"{what} would read {len(held)} Held-out case(s): pass an access log (path, who, why)"
        )
    log = require_access(access)
    access_log.append(
        log.path,
        who=log.who,
        why=f"{log.why} ({what})",
        run_id=uuid.uuid4().hex[:12],
        split=splits.HELD_OUT,
        count=len(held),
    )
    return len(held)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_cases() -> list[dict[str, Any]]:
    return list(_load(CASES))


def load_samples() -> list[dict[str, Any]]:
    return list(_load(SAMPLES_PATH))


def load_agent_labels() -> dict[str, Any]:
    data = dict(_load(AGENT_PATH))
    if data.get("label_source") != "agent_drafted" or data.get("human_confirmed") is not False:
        raise ValueError("the agent labels file must say agent_drafted and human_confirmed false")
    return data


def load_borderline_samples() -> list[dict[str, Any]]:
    return list(_load(BORDERLINE_SAMPLES_PATH))


def load_borderline_agent_labels() -> dict[str, Any]:
    """Agent-drafted labels of EVERY borderline candidate, keyed `case_id/candidate_id`."""
    data = dict(_load(BORDERLINE_AGENT_PATH))
    if data.get("label_source") != "agent_drafted" or data.get("human_confirmed") is not False:
        raise ValueError(
            "the borderline labels file must say agent_drafted and human_confirmed false"
        )
    return data


def borderline_agent_by_sample() -> dict[str, str]:
    labels = load_borderline_agent_labels()["labels"]
    return {
        s["sample_id"]: labels[f"{s['case_id']}/{s['candidate_id']}"]
        for s in load_borderline_samples()
    }


def norm_name(name: Any) -> str:
    """A reviewer name reduced to a skeleton for comparison: NFKC (fullwidth and composed forms),
    invisible format characters (zero-width space and joiner, BOM) and combining marks removed,
    punctuation treated as a space, case folded, whitespace collapsed. 'Ali.' == 'ali' == 'Ali  ',
    'Ali-Khan' == 'Ali Khan'. Code cannot prove two names are two people; this only stops the
    obvious accidents."""
    text = unicodedata.normalize("NFKC", str(name or ""))
    kept = []
    for ch in text:
        category = unicodedata.category(ch)
        if category in ("Cf", "Mn"):
            continue
        kept.append(" " if ch.isspace() or category.startswith(("P", "Z", "C")) else ch)
    return " ".join("".join(kept).casefold().split())


def known_sample_ids() -> set[str]:
    return {s["sample_id"] for s in load_samples()} | {
        s["sample_id"] for s in load_borderline_samples()
    }


def agent_labels_all() -> dict[str, str]:
    """Every agent-drafted label, core and borderline (never an input of a human comparison)."""
    return {**load_agent_labels()["labels"], **borderline_agent_by_sample()}


def check_human_labels(data: dict[str, Any]) -> dict[str, str]:
    """The checks every human label input passes, whether it is a file or a dict handed to a
    library function: label_source human, no `human_confirmed` set by the sheet itself, only known
    sample ids, only allowed verdicts, and not a copy of the agent-drafted labels."""
    if data.get("label_source") != "human":
        raise ValueError("a human labels input must say label_source: human")
    if "human_confirmed" in data:
        raise ValueError("a human labels input must not set human_confirmed itself")
    labels = data.get("labels")
    if not isinstance(labels, dict):
        raise ValueError("a human labels input needs a labels mapping")
    unknown = sorted(set(labels) - known_sample_ids())
    if unknown:
        raise ValueError(f"unknown sample ids: {unknown[:5]}")
    bad = sorted({str(v) for v in labels.values() if v not in relevance.VERDICTS})
    if bad:
        raise ValueError(f"not allowed verdicts: {bad[:5]}")
    agent = agent_labels_all()
    shared = [i for i in labels if i in agent]
    if len(shared) >= AGENT_COPY_MIN_SAMPLES:
        same = sum(1 for i in shared if agent[i] == labels[i])
        if same / len(shared) >= AGENT_COPY_LEVEL:
            raise ValueError(
                f"agent-copy suspected: {same} of {len(shared)} labels equal the agent-drafted ones"
            )
    return dict(labels)


def human_labels_problem(data: dict[str, Any]) -> str:
    """Why a human labels file cannot back a human comparison, or an empty string when it can:
    at least two DISTINCT normalised reviewer names, known ids, enough samples."""
    reviewers = data.get("reviewers")
    if not isinstance(reviewers, list):
        return "the file must name its reviewers as a list"
    names = [norm_name(r) for r in reviewers]
    if not names or not all(names):
        return "every reviewer must be named"
    if len(set(names)) < 2:
        return "at least two distinct reviewers are needed"
    try:
        labels = check_human_labels(data)
    except ValueError as exc:
        return str(exc)
    if len(labels) < MIN_HUMAN_SAMPLES:
        return f"at least {MIN_HUMAN_SAMPLES} labelled samples are needed (have {len(labels)})"
    return ""


def validate_grader(raw: Any) -> dict[str, str]:
    """A grader results mapping of sample id to an allowed verdict ('results' must be a mapping when
    present). Raises ValueError('invalid grader file: ...') instead of letting a bad shape crash."""
    data = raw
    if isinstance(raw, dict) and "results" in raw:
        data = raw["results"]
        if not isinstance(data, dict):
            raise ValueError("invalid grader file: 'results' must be a mapping of id to verdict")
    if isinstance(data, list):
        try:
            data = {r["sample_id"]: r["verdict"] for r in data}
        except (TypeError, KeyError) as exc:
            raise ValueError("invalid grader file: a list needs sample_id and verdict") from exc
    if not isinstance(data, dict) or not data:
        raise ValueError("invalid grader file: expected a mapping of sample id to verdict")
    bad = sorted(
        str(k) for k, v in data.items() if not isinstance(k, str) or v not in relevance.VERDICTS
    )
    if bad:
        raise ValueError(f"invalid grader file: not an allowed verdict for {bad[:5]}")
    return dict(data)


def load_human_labels(path: str | Path) -> dict[str, Any]:
    data = dict(_load(Path(path)))
    reviewers = data.get("reviewers")
    names = [norm_name(r) for r in reviewers] if isinstance(reviewers, list) else []
    if not names or not all(names):
        raise ValueError("a human labels file must name every reviewer")
    if len(set(names)) < 2:
        raise ValueError("a human labels file needs at least two distinct reviewers")
    check_human_labels(data)
    return data


def _index(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in cases}


def _candidate(case: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    return next(c for c in case["expected"]["candidates"] if c["id"] == candidate_id)


def blind_sheet(
    cases: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    seed: int = SEED,
    access: Access | None = None,
) -> list[dict[str, Any]]:
    """What a reader sees: the owner's words, stated facts and limits, and one idea. No label, no
    verdict, no reason, no scorer output and no blocking keyword. Order is shuffled, fixed seed."""
    by_id = _index(cases)
    guard([by_id[s["case_id"]] for s in samples], access, "blind_sheet")
    rows = []
    for sample in samples:
        case = by_id[sample["case_id"]]
        brief = case["input"]["brief"]
        rows.append(
            {
                "sample_id": sample["sample_id"],
                "industry": case["industry"],
                "language": case["language"],
                "owner_problem": " ".join(case["input"]["messages"]),
                "facts": [f for p in brief["problems"] for f in p["facts"]],
                "constraints": [
                    {"kind": c["kind"], "text": c["text"]}
                    for p in brief["problems"]
                    for c in p["constraints"]
                ],
                "candidate_idea": _candidate(case, sample["candidate_id"])["text"],
                "allowed_verdicts": list(relevance.VERDICTS),
            }
        )
    random.Random(seed).shuffle(rows)
    return rows


def human_rows(sheet: list[dict[str, Any]], block: str = "core") -> list[dict[str, Any]]:
    return [
        {
            "block": block,
            "sample_id": r["sample_id"],
            "language": r["language"],
            "owner_problem": r["owner_problem"],
            "facts": "; ".join(r["facts"]),
            "constraints": "; ".join(f"{c['kind']}: {c['text']}" for c in r["constraints"]),
            "candidate_idea": r["candidate_idea"],
            "allowed_verdicts": " / ".join(relevance.VERDICTS),
            "verdict": "",
            "notes": "",
        }
        for r in sheet
    ]


def _markdown(rows: list[dict[str, Any]]) -> str:
    out = [
        "# Human review sheet: candidate ideas",
        "",
        "For each row choose ONE verdict for the candidate idea, from the owner's words only.",
        "Write it in the verdict column. Do not discuss with the other reviewer until both finish.",
        "",
        "Allowed verdicts:",
        "",
    ]
    out += [f"- **{v}**: {DEFINITIONS[v]}" for v in relevance.VERDICTS]
    titles = {"core": "Block 1: core samples", "borderline": "Block 2: borderline samples"}
    for block in BLOCKS:
        part = [r for r in rows if r["block"] == block]
        if not part:
            continue
        out += [
            "",
            f"## {titles[block]}",
            "",
            "| id | language | owner's words | facts | limits | candidate idea | verdict | notes |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in part:
            cells = [r[k].replace("|", "/") for k in (
                "sample_id", "language", "owner_problem", "facts", "constraints", "candidate_idea"
            )]  # fmt: skip
            out.append("| " + " | ".join(cells) + " |  |  |")
    return "\n".join(out) + "\n"


def all_rows(
    access: Access | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """(core blind rows, borderline blind rows, every human row with its block)."""
    cases = load_cases()
    core = blind_sheet(cases, load_samples(), access=access)
    border = blind_sheet(cases, load_borderline_samples(), access=access)
    return core, border, human_rows(core, "core") + human_rows(border, "borderline")


def write_sheets(out_dir: str | Path, access: Access | None = None) -> list[Path]:
    """The blind grader sheets (core, borderline) and the human review sheet with both blocks
    (json, csv, markdown), side by side. No label, no scorer output, an empty verdict column."""
    folder = Path(out_dir)
    core, border, rows = all_rows(access)  # refuses before anything is written
    folder.mkdir(parents=True, exist_ok=True)
    paths = {
        "blind_samples.json": json.dumps(core, ensure_ascii=False, indent=1),
        "blind_samples_borderline.json": json.dumps(border, ensure_ascii=False, indent=1),
        "human_review_sheet.json": json.dumps(
            {
                "label_source": "human",
                "reviewers": [],
                "allowed_verdicts": list(relevance.VERDICTS),
                "definitions": DEFINITIONS,
                "blocks": list(BLOCKS),
                "rows": rows,
            },
            ensure_ascii=False,
            indent=1,
        ),
        "human_review_sheet.md": _markdown(rows),
    }
    written = []
    for name, body in paths.items():
        target = folder / name
        target.write_text(body, encoding="utf-8", newline="\n")
        written.append(target)
    csv_path = folder / "human_review_sheet.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    written.append(csv_path)
    return written


def _kappa(a: list[str], b: list[str]) -> float | None:
    n = len(a)
    if not n:
        return None
    observed = sum(1 for x, y in zip(a, b, strict=True) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum((ca[v] / n) * (cb[v] / n) for v in set(ca) | set(cb))
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1 - expected)


def agreement(
    first: dict[str, str], second: dict[str, str], languages: dict[str, str]
) -> dict[str, Any]:
    """Percent agreement and Cohen's kappa over the ids both sides labelled; per verdict (by the
    second side's verdict) and per language."""
    ids = sorted(set(first) & set(second))
    a = [first[i] for i in ids]
    b = [second[i] for i in ids]
    same = [x == y for x, y in zip(a, b, strict=True)]
    per_verdict = {}
    for verdict in sorted(set(b)):
        idx = [k for k, y in enumerate(b) if y == verdict]
        per_verdict[verdict] = {
            "n": len(idx),
            "percent": 100.0 * sum(1 for k in idx if same[k]) / len(idx),
        }
    per_language = {}
    for lang in sorted({languages.get(i, "?") for i in ids}):
        idx = [k for k, i in enumerate(ids) if languages.get(i, "?") == lang]
        per_language[lang] = {
            "n": len(idx),
            "percent": 100.0 * sum(1 for k in idx if same[k]) / len(idx),
        }
    return {
        "n": len(ids),
        "percent": 100.0 * sum(same) / len(ids) if ids else None,
        "kappa": _kappa(a, b),
        "per_verdict": per_verdict,
        "per_language": per_language,
    }


def scorer_labels(
    cases: list[dict[str, Any]], samples: list[dict[str, Any]], access: Access | None = None
) -> dict[str, str]:
    by_id = _index(cases)
    guard([by_id[s["case_id"]] for s in samples], access, "scorer_labels")
    out = {}
    for s in samples:
        case = by_id[s["case_id"]]
        cand = _candidate(case, s["candidate_id"])
        out[s["sample_id"]] = relevance.score_candidate(
            case["input"]["brief"],
            cand["text"],
            problem=cand.get("problem"),
            owner_text=" ".join(case["input"]["messages"]),
            language=case["language"],
        )["verdict"]
    return out


def borderline_comparison(access: Access) -> dict[str, Any]:
    """Scorer verdict against the agent-drafted label for the Development borderline candidates.
    Held-out borderline candidates are only counted: they are not scored here and their labels are
    not committed. Counting them is a Held-out read, so this itself requires the access log (path,
    who, why) and writes the line. A disagreement is a finding: neither the scorer nor the case is
    changed to remove it."""
    log = require_access(access)
    cases = [c for c in load_cases() if c.get("kind") == "borderline_relevance"]
    guard(cases, log, "borderline_comparison (candidates counted only)")
    labels = load_borderline_agent_labels()["labels"]
    sample_of = {
        f"{s['case_id']}/{s['candidate_id']}": s["sample_id"] for s in load_borderline_samples()
    }
    rows: list[dict[str, Any]] = []
    held = 0
    for case in cases:
        if splits.split_of(case) == splits.HELD_OUT:
            held += len(case["expected"]["candidates"])
            continue
        for cand in case["expected"]["candidates"]:
            key = f"{case['id']}/{cand['id']}"
            got = relevance.score_candidate(
                case["input"]["brief"],
                cand["text"],
                problem=cand.get("problem"),
                owner_text=" ".join(case["input"]["messages"]),
                language=case["language"],
            )["verdict"]
            rows.append(
                {
                    "sample_id": sample_of.get(key, ""),
                    "case_id": case["id"],
                    "candidate_id": cand["id"],
                    "language": case["language"],
                    "agent_drafted": labels[key],
                    "scorer": got,
                    "agree": got == labels[key],
                    "text": cand["text"],
                }
            )
    return {"development": rows, "held_out_candidates": held}


def _fmt(name: str, result: dict[str, Any]) -> list[str]:
    kappa = "n/a" if result["kappa"] is None else f"{result['kappa']:.2f}"
    percent = "n/a" if result["percent"] is None else f"{result['percent']:.0f}%"
    out = [f"{name}: {percent} agreement on {result['n']} samples, kappa {kappa}"]
    out += [
        f"    verdict {v}: {r['percent']:.0f}% of {r['n']}"
        for v, r in result["per_verdict"].items()
    ]
    out += [
        f"    language {k}: {r['percent']:.0f}% of {r['n']}"
        for k, r in result["per_language"].items()
    ]
    return out


def compare(grader: Any, human: dict[str, Any] | None = None, access: Access | None = None) -> str:
    """Agreement three ways without a human file (scorer, grader, agent_drafted), plus the human
    comparisons only when a human labels file is given. The label sources are never merged."""
    cases = load_cases()
    samples = load_samples() + load_borderline_samples()
    by_id = _index(cases)
    languages = {s["sample_id"]: by_id[s["case_id"]]["language"] for s in samples}
    scorer = scorer_labels(cases, samples, access)
    agent = agent_labels_all()
    lines = [
        f"Agreement on the {len(samples)} calibration samples (code and drafts, not quality)",
        "",
    ]
    pairs = [("scorer vs agent_drafted", scorer, agent)]
    try:
        graded = validate_grader(grader)
    except ValueError as exc:
        graded = {}
        lines += [f"{exc}; no grader comparison is shown.", ""]
    else:
        pairs += [("scorer vs grader", scorer, graded), ("grader vs agent_drafted", graded, agent)]
    if human is None:
        lines += [
            "No human labels provided. The 85% acceptance is the owner's decision; this tool only "
            "prints numbers.",
            "agent_drafted labels are drafts from the case design, not human labels.",
            "",
        ]
    else:
        problem = human_labels_problem(human)
        if problem:
            lines += [
                f"The human comparison is not valid: {problem}. No scorer, grader or "
                "agent_drafted comparison against human labels is printed.",
                "",
            ]
        else:
            labels = dict(human["labels"])
            names = [norm_name(r) for r in human.get("reviewers") or []]
            lines += [f"Human labels from reviewers {names} (normalised names).", IDENTITY_NOTE, ""]
            pairs += [
                ("scorer vs human", scorer, labels),
                ("agent_drafted vs human", agent, labels),
            ]
            if graded:
                pairs.append(("grader vs human", graded, labels))
    for name, one, two in pairs:
        lines += _fmt(name, agreement(one, two, languages)) + [""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sheets", default="", help="write the blind and human sheets to this folder"
    )
    parser.add_argument("--grader", default="", help="grader results JSON: id -> verdict")
    parser.add_argument("--human", default="", help="human labels JSON (separate input)")
    parser.add_argument("--access-log", default="", help="needed only if a Held-out case is read")
    parser.add_argument("--who", default="")
    parser.add_argument("--why", default="")
    args = parser.parse_args()
    access = Access(args.access_log, args.who, args.why) if args.access_log else None
    if args.sheets:
        for path in write_sheets(args.sheets, access):
            print("wrote", path)
    if args.grader:
        human = load_human_labels(args.human) if args.human else None
        print(compare(_load(Path(args.grader)), human, access))


if __name__ == "__main__":
    main()
