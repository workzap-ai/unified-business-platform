"""The journeys through the pure parts of the flow: the owner's record folded from the scripted
notes, the L2-1 gate, the blueprint builder and the decision gates (no database, no model).

`tests/integration/ps_journey_harness.py` feeds the same functions with what the real pipeline
stored, so the unit and the integration tests assert the same behaviour.
"""

import re
from typing import Any

from tests.support.ps_journey_checks import (
    figures_after_corrections,
    has_figure,
    money_or_promise,
    owner_texts,
)

LIMIT_KEYS = ("budget", "staff", "deadline")


# --- what the owner said, folded from the journey's scripted notes ------------------------------


def _cause(note: dict[str, Any]) -> dict[str, Any] | None:
    if not note.get("cause_text"):
        return None
    return {
        "text": note["cause_text"],
        "status": "owner_said" if note.get("cause_said") else "pi_inferred",
        "words": list(note.get("cause_words") or []),
    }


def fold_record(journey: dict[str, Any], upto: int | None = None) -> list[dict[str, Any]]:
    """The problems after the scripted notes of the first `upto` turns (all when None): what the
    owner stated, merged the way the book merges it (a said limit replaces the older one of its
    key, cannot_change and tried add up, a correction replaces the wording of the old figure)."""
    problems: list[dict[str, Any]] = []
    for n, turn in enumerate(journey["turns"]):
        if upto is not None and n >= upto:
            break
        for op in turn.get("ops") or []:
            note = dict(op["note"])
            if op["op"] == "create":
                problems.append(
                    {
                        "title": note.get("title", ""),
                        "category": note.get("category", ""),
                        "quotes": list(note.get("user_words") or []),
                        "where": ", ".join(note.get("where") or []) or note.get("of_total", ""),
                        "how_often": note.get("frequency_text", ""),
                        "since": note.get("since_text", ""),
                        "money": note.get("money_text", ""),
                        "limits": {k: note[k] for k in LIMIT_KEYS if note.get(k)},
                        "cannot_change": list(note.get("cannot_change") or []),
                        "tried": [dict(t) for t in note.get("tried") or []],
                        "cause": _cause(note),
                        "msgs": [n],
                    }
                )
                continue
            p = problems[op["problem"]]
            p["msgs"].append(n)
            for k in LIMIT_KEYS:
                if note.get(k):
                    p["limits"][k] = note[k]
            p["cannot_change"] += [
                c for c in note.get("cannot_change") or [] if c not in p["cannot_change"]
            ]
            p["tried"] += [dict(t) for t in note.get("tried") or []]
            for key, field in (("since", "since_text"), ("how_often", "frequency_text")):
                if note.get(field):
                    p[key] = note[field]
            if note.get("of_total"):
                p["where"] = note["of_total"]
            if note.get("user_words"):
                if op.get("reason") == "correction":
                    p["quotes"] = list(note["user_words"]) + p["quotes"][1:]
                else:
                    p["quotes"] += list(note["user_words"])
            if _cause(note):
                p["cause"] = _cause(note)
        _net_correction(journey, n, problems)
    return problems


def _net_correction(journey: dict[str, Any], n: int, problems: list[dict[str, Any]]) -> None:
    """The book's own safety net: an owner who corrects a figure ("not 10, 20") has the old figure
    replaced in what is stored, whether or not the model wrote a correction note."""
    from app.modules.pi import figure_correction as fc

    texts = owner_texts(journey)
    fix = fc.numeric_correction(texts[n], texts[max(0, n - 3) : n])
    if not fix:
        return
    wrong, right = fix
    for p in problems:
        p["quotes"] = [fc.replace_figure(q, wrong, right) for q in p["quotes"]]
        for key in ("where", "how_often", "money"):
            p[key] = fc.replace_figure(p[key], wrong, right)


def requirements_data(problems: list[dict[str, Any]]) -> dict[str, Any]:
    """The plain data `option_wiring.requirements_from` reads, from folded problems."""
    data: dict[str, Any] = {"columns_available": True, "cannot_change": [], "tried": []}
    for key in LIMIT_KEYS:
        data[key] = [p["limits"][key] for p in problems if p["limits"].get(key)]
    for p in problems:
        data["cannot_change"] += p["cannot_change"]
        data["tried"] += p["tried"]
    if not any(data[k] for k in (*LIMIT_KEYS, "cannot_change", "tried")):
        return {}
    return data


def synthetic_views(journey: dict[str, Any], upto: int | None = None) -> list[dict[str, Any]]:
    """Views shaped like `box_doc.problem_view` over the folded record (message ids m<turn>)."""
    views = []
    for i, p in enumerate(fold_record(journey, upto), start=1):
        cause = p["cause"] or {}
        views.append(
            {
                "ref": f"P{i}",
                "id": f"id-{i}",
                "title": p["title"],
                "category": p["category"],
                "quotes": p["quotes"][:2],
                "where": p["where"],
                "how_often": p["how_often"],
                "since": p["since"],
                "money": p["money"],
                "impact": [],
                "cause": "",
                "rank": 0,
                "limits": dict(p["limits"]),
                "cannot_change": list(p["cannot_change"]),
                "tried": list(p["tried"]),
                "cause_text": cause.get("text", ""),
                "cause_status": cause.get("status", ""),
                "expected_outcome": "",
                "msgs": [f"m{n}" for n in p["msgs"]],
            }
        )
    return views


def synthetic_owner_messages(journey: dict[str, Any]) -> dict[str, str]:
    return {f"m{n}": t for n, t in enumerate(owner_texts(journey))}


# --- ideas through the real gate and the real blueprint -----------------------------------------


def verdict(idea_text: str, req_data: dict[str, Any], language: str) -> Any:
    from app.modules.pi import constraint_check as cc
    from app.modules.pi import option_wiring

    return cc.check_option(idea_text, option_wiring.requirements_from(req_data), language)


def components(journey: dict[str, Any], refs: list[str]) -> list[dict[str, Any]]:
    """One blueprint component per idea; its refs are the problems the idea names (an unrelated
    idea has none). All in phase 1, so a step number is the idea's position + 1."""
    from app.modules.pi import solutions

    key = next(iter(solutions.CATALOGUE))
    return [
        {
            "key": key,
            "text": idea["text"],
            "phase": 1,
            "refs": [refs[r] for r in idea["refs"] if r < len(refs)],
        }
        for idea in journey["ideas"]
    ]


def build_blueprint(
    journey: dict[str, Any],
    views: list[dict[str, Any]],
    owner_messages: dict[str, str],
) -> dict[str, Any]:
    from app.modules.pi import blueprint_doc

    comps = components(journey, [v["ref"] for v in views])
    phases = [{"phase": 1, "name": "First"}]
    return blueprint_doc.build(
        views, comps, phases, ["a contact person"], owner_messages=owner_messages
    )


def recommended_idea(journey: dict[str, Any], bp: dict[str, Any]) -> int | None:
    """The position of the idea the blueprint recommends (None when it recommends none, or the
    'learn more first' step)."""
    option = bp["recommendation"].get("option") or ""
    for n, idea in enumerate(journey["ideas"]):
        if option and option == idea["text"]:
            return n
    return None


def doc_text(bp: dict[str, Any]) -> str:
    """Every word of the document a reader sees (no step numbers, no refs)."""
    parts = []
    for p in bp["problems"]:
        parts += [p["title"], *p["owner_words"], *p["figures"], *p["limits"], *p["tried"]]
        parts += [(p["cause"] or {}).get("text", ""), p.get("expected_outcome", "")]
    rec = bp["recommendation"]
    parts += [s["text"] for s in bp["steps"]] + [
        re.sub(r"Step \d+", "Step", r["text"]) for r in bp["risks"]
    ]
    parts += [rec.get("option", ""), rec.get("why", ""), rec.get("reason", "")]
    parts += list(rec.get("trade_offs") or []) + list(rec.get("unknown") or [])
    parts += [r["because"] for r in rec.get("rejected") or []]
    parts += list(bp.get("unresolved") or [])
    return "\n".join(p for p in parts if p)


COMPONENTS = (
    "traceable",
    "violating_never_recommended",
    "unknown_never_clear",
    "generic_never_recommended",
    "figures",
    "limits",
    "no_price_or_promise",
    "risk_quotes_owner_limit",
    "evidence_survives_correction",
    "causes_labelled",
)


def blueprint_findings(
    journey: dict[str, Any], bp: dict[str, Any], views: list[dict[str, Any]]
) -> dict[str, list[str]]:
    """What is wrong with the blueprint for this journey, by component (empty list = fine)."""
    from app.modules.pi import blueprint_doc

    found: dict[str, list[str]] = {k: [] for k in COMPONENTS}
    ideas = journey["ideas"]
    refs = [v["ref"] for v in views]
    steps = {s["text"]: s for s in bp["steps"]}
    # a step with no problem is flagged; every problem has at least one linked step
    flagged = sorted(bp["unlinked_steps"])
    wanted = sorted(n for n, i in enumerate(ideas, start=1) if not i["refs"])
    if flagged != wanted:
        found["traceable"].append(f"unlinked steps {flagged}, expected {wanted}")
    linked_refs = {r for s in bp["steps"] for r in s["problems"]}
    if linked_refs != set(refs):
        found["traceable"].append(f"problems without a step: {sorted(set(refs) - linked_refs)}")
    for text in blueprint_doc.issues(bp):
        if "unlinked" in text:
            continue
        if "holds a price" in text and any(
            money_or_promise(i["text"]) and i["text"][:40] in text for i in ideas
        ):
            continue  # an idea that names an amount is flagged, not silently shown
        if "holds a price" in text and "clashes with what you said" in text:
            found["risk_quotes_owner_limit"].append(text)  # the owner's own figure, quoted back
            continue
        found["no_price_or_promise"].append(text)
    # the document is checked on pi's own words only (an idea that names an amount is flagged above)
    clean = [s["text"] for s in bp["steps"] if not money_or_promise(s["text"])]
    why = re.sub(
        r"(?<![0-9a-f])[0-9a-f]{8}(?![0-9a-f])", "<ref>", bp["recommendation"].get("why", "")
    )
    for text in [*clean, why]:
        if money_or_promise(text):
            found["no_price_or_promise"].append(text[:60])
    rec = recommended_idea(journey, bp)
    for n, idea in enumerate(ideas):
        step = steps.get(idea["text"])
        if step is None:
            found["traceable"].append(f"idea {n} has no step")
            continue
        status = step["check"]["status"]
        if idea["must"] == "reject" and rec == n:
            found["violating_never_recommended"].append(idea["text"][:60])
        if idea["must"] == "reject" and status == "ok":
            found["violating_never_recommended"].append(f"checked ok: {idea['text'][:50]}")
        if idea["must"] == "unknown" and status == "ok":
            found["unknown_never_clear"].append(idea["text"][:60])
        if idea["must"] == "generic" and rec == n:
            found["generic_never_recommended"].append(idea["text"][:60])
    packed = doc_text(bp)
    kept, gone = figures_after_corrections(journey)
    body = " ".join(" ".join(p["figures"] + p["owner_words"] + p["limits"]) for p in bp["problems"])
    for fig in kept:
        if not has_figure(body, fig):
            found["figures"].append(f"kept figure {fig} missing from the document")
    for fig in gone:
        if has_figure(packed, fig):
            found["figures"].append(f"corrected figure {fig} still in the document")
    limits = journey["expect"].get("limits") or {}
    shown = " ".join(" ".join(p["limits"]) for p in bp["problems"])
    for key in LIMIT_KEYS:
        if limits.get(key) and limits[key] not in shown:
            found["limits"].append(f"{key} limit not in the document")
    for sub in limits.get("cannot") or []:
        if sub not in shown:
            found["limits"].append(f"cannot-change '{sub}' not in the document")
    usable = [i for i in ideas if i["refs"] and i["must"] in ("not_rejected", "unknown")]
    if usable and bp["recommendation"].get("learn_first"):
        found["evidence_survives_correction"].append(
            "the blueprint says learn more first although the owner gave a clear problem"
        )
    for p in bp["problems"]:
        c = p["cause"]
        if c and not c["owner_stated"] and c["label"] != blueprint_doc.HYPOTHESIS:
            found["causes_labelled"].append(p["ref"])
    return found


# --- the gate, by component, and what the lanes have not landed yet ------------------------------

NON_LATIN = ("ur", "ar")
LOCALISED = (
    "constraint_check word rules read English and Roman Urdu only: an Urdu or Arabic idea that "
    "breaks a limit is 'unknown' and can be recommended (localised constraint check not landed)"
)
MISSING_BUDGET = (
    "FINDING no budget was stated and the idea clearly costs money: the gate says 'ok' where the "
    "brief wants 'unknown'"
)
RISK_QUOTES = (
    "FINDING blueprint_doc.issues() reports 'holds a price or saving' for the risk 'Step n clashes "
    "with what you said: it goes past the budget you gave (Rs 50,000)' (the owner's own budget)"
)
EVIDENCE_AFTER_CORRECTION = (
    "FINDING blueprint_doc.options() checks a problem's quote words against its FIRST source "
    "message; after a corrected figure the quote holds the new figure, the evidence fails and the "
    "blueprint says learn more first"
)
TRIED_ROMAN = (
    "FINDING a Roman Urdu outcome 'mix ho gaye' (what the owner tried) is not read as a failure"
)


ASKS_KNOWN = (
    "FINDING the no-idea fallback ('I don't have a quick idea... What have you tried so far?') "
    "asks what the owner tried although the record holds it: targeted-question selector (PS-5) "
    "not landed"
)
FALLBACK_ENGLISH = (
    "FINDING the no-idea fallback ('Yes. I don't have a quick idea for this one...') is sent in "
    "English to an Urdu-script owner (Roman Urdu has its own line)"
)


def gate_findings(journey: dict[str, Any], req_data: dict[str, Any]) -> dict[str, list[str]]:
    """The L2-1 gate over the stated limits, by component (empty list = fine)."""
    found: dict[str, list[str]] = {
        "gate_reject": [],
        "gate_never_ok": [],
        "gate_unknown": [],
        "gate_not_rejected": [],
    }
    language = journey["language"]
    for n, idea in enumerate(journey["ideas"]):
        v = verdict(idea["text"], req_data, language)
        label = f"idea {n}: {v.status}/{v.rule}"
        if idea["must"] == "reject":
            if v.status != "violates":
                found["gate_reject"].append(label)
            if v.status == "ok":
                found["gate_never_ok"].append(label)
        elif idea["must"] == "unknown" and v.status != "unknown":
            found["gate_unknown"].append(label)
        elif idea["must"] == "not_rejected" and v.status == "violates":
            found["gate_not_rejected"].append(label)
    return found


def pending_components(journey: dict[str, Any]) -> dict[str, str]:
    """Components of this journey that depend on behaviour not landed yet, with the reason."""
    out: dict[str, str] = {}
    ideas = journey["ideas"]
    if journey["language"] in NON_LATIN and any(i["must"] == "reject" for i in ideas):
        out["gate_reject"] = LOCALISED
        out["violating_never_recommended"] = LOCALISED
    if journey["id"] == "clinic_roman_ur":
        out["gate_reject"] = TRIED_ROMAN
    if any(i.get("limit") == "missing_budget" for i in ideas):
        out["gate_unknown"] = MISSING_BUDGET
        out["unknown_never_clear"] = MISSING_BUDGET
    if any(i.get("limit") == "budget" for i in ideas) and journey["language"] not in NON_LATIN:
        out["risk_quotes_owner_limit"] = RISK_QUOTES
    if "corrections" in journey["difficulty"]:
        out["evidence_survives_correction"] = EVIDENCE_AFTER_CORRECTION
    if journey["rerank"] and journey["language"] in NON_LATIN:
        out["rerank"] = LOCALISED
    if journey["expect"].get("tried"):
        out["reply_asks_known"] = ASKS_KNOWN
    if journey["language"] == "ur":
        out["replies_language"] = FALLBACK_ENGLISH
    return out
