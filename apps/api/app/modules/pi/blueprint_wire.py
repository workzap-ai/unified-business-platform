"""PS-flow: the document blueprint, built by PS-4 (`blueprint_build`) from the owner record,
with the recommendation chosen by the same L2-3 ranking the chat uses (`option_rank`).

`option_set` ranks three honest candidates: the Solution Box (what Workzap would build), the idea
the chat already recommended to the owner (if any) and `learn_first`. A box with no verified owner
evidence cannot be recommended, so a thin record recommends learning first, not building.
`build` returns plain JSON for `content["blueprint"]`: the localized text for the reviewer, the
status, the one next question, and the checked issues (any issue blocks approval).
"""

from collections.abc import Mapping
from typing import Any

from app.modules.pi import blueprint_models as bm
from app.modules.pi import blueprint_rules as br
from app.modules.pi import constraint_check as cc
from app.modules.pi import option_rank, option_wiring
from app.modules.pi.blueprint_build import (
    blueprint_issues,
    build_blueprint,
    render_blueprint,
)
from app.modules.pi.requirements_types import Requirements

LIMIT_KEYS = ("budget", "staff", "deadline")


def requirements_of(views: list[dict[str, Any]]) -> Requirements:
    """The owner's stated limits and tried-before, from the views, for the constraint check."""
    data: dict[str, Any] = {"columns_available": True, "cannot_change": [], "tried": []}
    for key in LIMIT_KEYS:
        data[key] = [v["limits"][key] for v in views if (v.get("limits") or {}).get(key)]
    for v in views:
        data["cannot_change"] += list(v.get("cannot_change") or [])
        data["tried"] += list(v.get("tried") or [])
    if not any(data[k] for k in (*LIMIT_KEYS, "cannot_change", "tried")):
        return Requirements()
    return option_wiring.requirements_from(data)


def _words(quote: str) -> tuple[str, ...]:
    return tuple(w for w in quote.replace(",", " ").split() if len(w) >= 3)[:3]


def _evidence(views: list[dict[str, Any]]) -> tuple[bm.Evidence, ...]:
    return tuple(
        bm.Evidence(msg, _words(v["quotes"][0]))
        for v in views
        for msg in (v.get("msgs") or [])[:1]
        if v.get("quotes")
    )


def _aggregate(checks: list[cc.Verdict]) -> tuple[str, str]:
    for status in ("violates", "unknown"):
        for c in checks:
            if c.status == status:
                return status, c.reason
    return "ok", ""


def option_set(
    views: list[dict[str, Any]],
    components: list[dict[str, Any]],
    owner_messages: dict[str, str] | None,
    chat_pick: str = "",
) -> tuple[bm.OptionSet, list[dict[str, Any]]]:
    """The ranked options, and the steps (components in phase order) with their own checks."""
    reqs = requirements_of(views)
    ordered = sorted(components, key=lambda c: int(c.get("phase") or 1))
    steps: list[dict[str, Any]] = []
    verdicts: list[cc.Verdict] = []
    for n, comp in enumerate(ordered, start=1):
        v = cc.check_option(str(comp.get("text") or ""), reqs)
        verdicts.append(v)
        phase = int(comp.get("phase") or 1)
        steps.append(
            {
                "id": f"S{n}",
                "text": str(comp.get("text") or ""),
                "role": "staff",
                "phase": phase,
                "after": [s["id"] for s in steps if s["phase"] == phase - 1],
                "problems": list(comp.get("refs") or []),
                "check": v.status,
            }
        )
    status, reason = _aggregate(verdicts)
    refs = tuple(v["ref"] for v in views)
    box = bm.Option(
        id="BOX",
        kind="workzap_build",
        what="; ".join(s["text"] for s in steps[:4]) or "Solution Box",
        addresses=refs,
        benefit="Answers " + ", ".join(refs) if refs else "",
        effort="medium",  # not known: it never decides the ranking by itself
        reversibility="partly",
        status="rejected" if status == "violates" else "alternative",
        catalogue_key="solution_box",
        evidence=_evidence(views),
        constraint_checks=(bm.ConstraintCheck("stated limits", status, reason),),
        rejected_because=reason if status == "violates" else "",
    )
    built = [box]
    if chat_pick:
        v = cc.check_option(chat_pick, reqs)
        built.append(
            option_rank.idea_option(
                0,
                chat_pick,
                v.status,
                v.reason,
                addresses=refs,
                evidence=_evidence(views),
                prefix="CHAT",
            )
        )
    built.append(
        bm.Option(
            id="LEARN",
            kind=bm.LEARN_FIRST,
            what="Learn more from you before building anything",
            addresses=refs,
            benefit="Fills the gaps listed as unresolved",
            effort="small",
            reversibility="reversible",
        )
    )
    ranked = br.rank_options(built, owner_messages)
    first = next((o for o in ranked if br.recommendable(o, owner_messages)), None)
    if first is None and br.evidence_thin(ranked, owner_messages):
        first = next(o for o in ranked if o.kind == bm.LEARN_FIRST)
    none_reason = (
        "" if first else "No option is both clear of your limits and backed by what you said."
    )
    final = tuple(
        option_rank.marked(o, "recommended") if first and o.id == first.id else o for o in ranked
    )
    oset = bm.OptionSet(
        options=final,
        recommended_id=first.id if first else None,
        no_recommendation_reason=none_reason,
    )
    return oset, steps


def _recommended(oset: bm.OptionSet, steps: list[dict[str, Any]]) -> Any:
    """What PS-4 reads as the recommendation. The Solution Box carries its steps and modules; any
    other option (the chat pick, learn first) goes in as the L2-3 set itself."""
    top = next((o for o in oset.options if o.id == oset.recommended_id), None)
    if top is None or top.id != "BOX":
        return oset
    return {
        "id": top.id,
        "kind": top.kind,
        "what": top.what,
        "addresses": list(top.addresses),
        "benefit": top.benefit,
        "effort": top.effort,
        "status": "recommended",
        "reversibility": top.reversibility,
        "steps": steps,
        "modules": [s["text"] for s in steps][:6],
        "constraint_checks": [
            {"constraint": c.constraint, "result": c.result, "why": c.why}
            for c in top.constraint_checks
        ],
        "catalogue_key": top.catalogue_key,
    }


def build(
    views: list[dict[str, Any]],
    components: list[dict[str, Any]],
    needs: list[str],
    owner_messages: dict[str, str] | None,
    language: str = "en",
    chat_pick: str = "",
    staff_inputs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """`content["blueprint"]`: status, localized text, the one next question, the issues."""
    oset, steps = option_set(views, components, owner_messages, chat_pick)
    problems = [
        {
            "id": v["ref"],
            "title": v["title"],
            "user_words": list(v.get("quotes") or []),
            "of_total": v.get("of_total", ""),
            "frequency_text": v.get("how_often", ""),
            "since_text": v.get("since", ""),
            "expected_outcome": v.get("expected_outcome", ""),
        }
        for v in views
    ]
    constraints = [
        {"kind": k, "text": t} for v in views for k, t in (v.get("limits") or {}).items()
    ] + [{"kind": "cannot_change", "text": t} for v in views for t in v.get("cannot_change") or []]
    requirements = {
        "constraints": constraints,
        "tried": [t for v in views for t in v.get("tried") or []],
        "expected_outcome": {
            v["ref"]: v["expected_outcome"] for v in views if v.get("expected_outcome")
        },
    }
    causes = {v["ref"]: v["cause_raw"] for v in views if v.get("cause_raw")}
    facts = list((owner_messages or {}).values()) + [
        q for v in views for q in v.get("quotes") or []
    ]
    bp = build_blueprint(
        _recommended(oset, steps),
        problems,
        requirements,
        facts,
        language,
        staff_inputs,
        root_causes=causes or None,
        options=oset,
    )
    issues = blueprint_issues(bp, facts, problems, requirements, staff_inputs, causes or None)
    return {
        "status": bp.status,
        "language": bp.language,
        "text": render_blueprint(bp, language),
        "next_question": bp.next_question,
        "refusal": list(bp.refusal),
        "recommended": oset.recommended_id or "",
        "issues": [f"{i.code}: {i.text}" for i in issues],
    }
