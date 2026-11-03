"""Evaluation helpers for language_script (agent 8), loaded by path from the tests.

`labelled.tsv` was written before the detector and then used to fix it: its numbers are a
development measure, not a held-out one. `ps0_dev_turns.json` holds the owner turns of the PS-0
Development split only (from `git archive pi/ps0-baseline`, split_of() == development)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from app.modules.pi import language_script as ls

DATA = Path(__file__).parent


def family(code: str) -> str:
    return "roman" if code in ls.ROMAN_INDIC else code


def load_labelled() -> list[tuple[str, tuple[str, ...], str]]:
    rows = []
    for line in (DATA / "labelled.tsv").read_text(encoding="utf8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        label, present, text = line.split("\t", 2)
        rows.append((label, tuple(p for p in present.split(",") if p), text))
    return rows


def load_ps0() -> list[dict]:
    return json.loads((DATA / "ps0_dev_turns.json").read_text(encoding="utf8"))


def expected_family(label: str) -> str:
    return "roman" if label in ("roman_ur", "roman_hi", "roman_ur_or_hi") else label


def predicted_family(text: str) -> str:
    d = ls.detect_message_language(text)
    return "und" if d.uncertain else family(d.code)


def labelled_report() -> dict[str, dict[str, float]]:
    rows = load_labelled()
    tp: Counter[str] = Counter()
    fp: Counter[str] = Counter()
    fn: Counter[str] = Counter()
    n: Counter[str] = Counter()
    for label, _present, text in rows:
        exp = expected_family(label)
        got = predicted_family(text)
        n[exp] += 1
        if got == exp:
            tp[exp] += 1
        else:
            fn[exp] += 1
            fp[got] += 1
    out = {}
    for lang in n:
        p = tp[lang] / (tp[lang] + fp[lang]) if tp[lang] + fp[lang] else 0.0
        r = tp[lang] / n[lang]
        out[lang] = {"n": n[lang], "precision": round(p, 3), "recall": round(r, 3)}
    return out


def present_report() -> dict[str, float]:
    tp = fp = fn = 0
    n = 0
    for _label, present, text in load_labelled():
        if not present:
            continue
        n += 1
        got = {family(c) for c in ls.detect_message_language(text).present}
        want = {family(c) for c in present}
        tp += len(got & want)
        fp += len(got - want)
        fn += len(want - got)
    return {
        "n": n,
        "precision": round(tp / (tp + fp), 3) if tp + fp else 0.0,
        "recall": round(tp / (tp + fn), 3) if tp + fn else 0.0,
    }


def ps0_report() -> dict[str, dict[str, float]]:
    tot: Counter[str] = Counter()
    ok: Counter[str] = Counter()
    unc: Counter[str] = Counter()
    wrong: Counter[str] = Counter()
    strict: Counter[str] = Counter()
    for case in load_ps0():
        lab = case["language"]
        exp = expected_family(lab)
        for m in case["messages"]:
            d = ls.detect_message_language(m)
            tot[lab] += 1
            if d.uncertain:
                unc[lab] += 1
            elif family(d.code) == exp:
                ok[lab] += 1
            else:
                wrong[lab] += 1
            if d.code == lab and not d.uncertain:
                strict[lab] += 1
    return {
        lab: {
            "n": tot[lab],
            "correct": ok[lab],
            "uncertain": unc[lab],
            "wrong": wrong[lab],
            "strict_code_match": strict[lab],
        }
        for lab in tot
    }


def ps0_sequence_flips() -> list[tuple[str, int, str, str]]:
    """Walk every Development case message by message, the pin built from earlier owner messages:
    every message whose reply (code, script) leaves the case language family or script."""
    flips = []
    for case in load_ps0():
        lab = case["language"]
        want_script = {"ur": "arabic", "ar": "arabic", "hi": "devanagari"}.get(lab, "latin")
        hist: list[str] = []
        for i, m in enumerate(case["messages"]):
            d = ls.detect_message_language(m, history=hist)
            code, script = ls.reply_language_for(d, None, hist)
            if script != want_script or (
                family(code) != expected_family(lab)
                and not (lab == "roman_ur" and family(code) == "roman")
            ):
                flips.append((case["id"], i, code, script))
            hist.append(m)
    return flips
