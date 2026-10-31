"""PS-flow: the solution blueprint of the document the reviewer reads, built in code.

Pure functions over the problem views (`box_doc.problem_view`) and the stored box components. No
model, no database. Nothing here is invented: every step, risk and criterion is derived from the
owner's stored words and figures or from the approved catalogue, and carries the problem it
answers. A step that answers no problem is labelled unlinked and flagged. Cost is never written
(staff only), nothing is promised, and a cause pi guessed stays labelled a hypothesis.

`build` returns the dict stored as `content["blueprint"]`; `issues` re-checks a stored one.
"""

import dataclasses
from typing import Any

from app.modules.pi import blueprint_models as bm
from app.modules.pi import blueprint_rules as br
from app.modules.pi import blueprint_text as bt
from app.modules.pi import constraint_check as cc
from app.modules.pi import option_wiring
from app.modules.pi.requirements_types import Requirements

HYPOTHESIS = "Our guess, not confirmed by you"
OWNER_CAUSE = "As you said"
LIMIT_KEYS = ("budget", "staff", "deadline")


def _words(quote: str) -> tuple[str, ...]:
    return tuple(w for w in quote.replace(",", " ").split() if len(w) >= 3)[:3]


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


def problem_records(views: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each problem in the owner's words with its figures, limits, tried-before, cause status and
    wanted outcome. Owner-stated and pi-generated things sit in separate keys."""
    out: list[dict[str, Any]] = []
    for v in views:
        status = v.get("cause_status") or ""
        cause = v.get("cause_text") or v.get("cause") or ""
        owner_cause = bool(cause) and (
            status in bm.OWNER_STATUSES or (not status and v.get("cause"))
        )
        figures = (
            ("where", v.get("where")),
            ("how often", v.get("how_often")),
            ("since", v.get("since")),
            ("cost, in your words", v.get("money")),
        )
        tried = [
            t["what"] + (f" ({t['outcome']})" if t.get("outcome") else "")
            for t in v.get("tried") or []
        ]
        out.append(
            {
                "ref": v["ref"],
                "id": v.get("id", ""),
                "title": v["title"],
                "owner_words": list(v.get("quotes") or []),
                "figures": [f"{name}: {val}" for name, val in figures if val],
                "limits": [f"{k}: {t}" for k, t in (v.get("limits") or {}).items()]
                + [f"cannot change: {t}" for t in v.get("cannot_change") or []],
                "tried": tried,
                "cause": (
                    {
                        "text": cause,
                        "label": OWNER_CAUSE if owner_cause else HYPOTHESIS,
                        "owner_stated": owner_cause,
                    }
                    if cause
                    else None
                ),
                "expected_outcome": v.get("expected_outcome") or "",
            }
        )
    return out


def build(
    views: list[dict[str, Any]],
    components: list[dict[str, Any]],
    phases: list[dict[str, Any]],
    needs: list[str],
    *,
    owner_messages: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Steps, dependencies, roles, risks, milestones, acceptance criteria and the recommendation."""
    by_ref = {v["ref"]: v for v in views}
    reqs = requirements_of(views)
    ordered = sorted(components, key=lambda c: int(c.get("phase") or 1))
    steps: list[dict[str, Any]] = []
    for n, comp in enumerate(ordered, start=1):
        refs = [r for r in comp.get("refs") or [] if r in by_ref]
        phase = int(comp.get("phase") or 1)
        verdict = cc.check_option(str(comp.get("text") or ""), reqs)
        steps.append(
            {
                "n": n,
                "key": str(comp.get("key") or ""),
                "text": str(comp.get("text") or ""),
                "phase": phase,
                "problems": refs,
                "owner_words": [w for r in refs for w in (by_ref[r].get("quotes") or [])[:1]],
                "depends_on": [s["n"] for s in steps if s["phase"] == phase - 1],
                "needs_from_owner": list(needs) if phase == 1 else [],
                "roles": {"builds": "Workzap", "approves": "Workzap reviewer", "provides": "you"},
                "check": {"status": verdict.status, "reason": verdict.reason},
                "linked": bool(refs),
            }
        )
    risks: list[dict[str, str]] = []
    for rec in problem_records(views):
        if rec["cause"] and not rec["cause"]["owner_stated"]:
            text = f"The cause of {rec['title']} is our guess, so this may not remove it."
            risks.append({"ref": rec["ref"], "text": text})
    for s in steps:
        where = ",".join(s["problems"])
        if s["check"]["status"] == "violates":
            text = f"Step {s['n']} clashes with what you said: {s['check']['reason']}"
            risks.append({"ref": where, "text": text})
        elif s["check"]["status"] == "unknown":
            risks.append(
                {"ref": where, "text": f"Step {s['n']} is not yet checked against your limits."}
            )
    milestones = [
        {
            "phase": p["phase"],
            "name": p.get("name") or f"Phase {p['phase']}",
            "steps": [s["n"] for s in steps if s["phase"] == p["phase"]],
        }
        for p in phases
    ]
    acceptance: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for v in views:
        figure = "; ".join(x for x in (v.get("how_often"), v.get("money"), v.get("since")) if x)
        if v.get("expected_outcome"):
            acceptance.append(
                {
                    "ref": v["ref"],
                    "criterion": f"The result you asked for: {v['expected_outcome']}",
                    "baseline": figure,
                    "measurable": bool(figure),
                }
            )
            if not figure:
                unresolved.append(f"{v['title']}: no figure from you yet to measure it against.")
        else:
            unresolved.append(f"{v['title']}: you have not said what result you want.")
    oset = options(views, steps, owner_messages)
    top = next((o for o in oset.options if o.id == oset.recommended_id), None)
    return {
        "problems": problem_records(views),
        "steps": steps,
        "milestones": milestones,
        "risks": risks,
        "acceptance": acceptance,
        "unresolved": unresolved,
        "recommendation": {
            "option": top.what if top else "",
            "kind": top.kind if top else "",
            "trade_offs": [t for t in top.trade_offs if t] if top else [],
            "reason": oset.no_recommendation_reason or oset.none_reason,
            "learn_first": bool(top and top.kind == bm.LEARN_FIRST),
            "why": _why(top, oset, owner_messages),
            "unknown": [
                f"{o.what}: not yet checked against your limits"
                for o in oset.options
                if o.status != "rejected" and o.unknown_checks
            ]
            + list(unresolved),
            "options_seen": len(oset.options) - 1,
            "insufficient": len([o for o in oset.options if o.kind != bm.LEARN_FIRST]) < 2,
            "rejected": [
                {"option": o.what, "because": o.rejected_because}
                for o in oset.options
                if o.status == "rejected"
            ],
        },
        "unlinked_steps": [s["n"] for s in steps if not s["linked"]],
    }


def _why(top: bm.Option | None, oset: bm.OptionSet, owner_messages: dict[str, str] | None) -> str:
    """Why this option leads, from the record only: what it answers, how much of it the owner
    said (verified messages), whether it is clear of the stated limits."""
    if top is None:
        return oset.no_recommendation_reason
    if top.kind == bm.LEARN_FIRST:
        return "Nothing you told us yet backs a build, so the first step is to learn more from you."
    seen = br.strength(top, owner_messages)
    clear = (
        "clear of the limits you stated"
        if not top.unknown_checks
        else "not yet checked against all your limits"
    )
    return (
        f"It answers {', '.join(top.addresses)}, rests on {seen} message(s) you wrote, "
        f"and is {clear}."
    )


def options(
    views: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    owner_messages: dict[str, str] | None,
) -> bm.OptionSet:
    """One Option per step, ranked by `blueprint_rules.rank_options`. A step that clashes with a
    stated limit is rejected with its reason and never recommended; one without verified owner
    evidence cannot be recommended, so a thin record gives `learn_first` (honest, not a guess)."""
    by_ref = {v["ref"]: v for v in views}
    built: list[bm.Option] = []
    for s in steps:
        evidence = tuple(
            bm.Evidence(msg, _words(by_ref[r]["quotes"][0]))
            for r in s["problems"]
            for msg in (by_ref[r].get("msgs") or [])[:1]
            if by_ref[r].get("quotes")
        )
        violated = s["check"]["status"] == "violates"
        checks = (bm.ConstraintCheck("stated limits", s["check"]["status"], s["check"]["reason"]),)
        built.append(
            bm.Option(
                id=f"S{s['n']}",
                kind="workzap_build",
                what=s["text"],
                addresses=tuple(s["problems"]),
                benefit=f"Answers {', '.join(s['problems'])}" if s["problems"] else "",
                effort="medium",  # not known: all alike, so it never decides the ranking
                reversibility="partly",
                status="rejected" if violated else "alternative",
                catalogue_key=s.get("key") or "catalogue",
                evidence=evidence,
                constraint_checks=checks,
                rejected_because=s["check"]["reason"] if violated else "",
                trade_offs=("Needs your input first.",) if s["needs_from_owner"] else (),
            )
        )
    built.append(
        bm.Option(
            id="LEARN",
            kind=bm.LEARN_FIRST,
            what="Learn more from you before building anything",
            addresses=tuple(by_ref),
            benefit="Fills the gaps listed as unresolved",
            effort="small",
            reversibility="reversible",
        )
    )
    ranked = br.rank_options(built, owner_messages)
    first = next((o for o in ranked if br.recommendable(o, owner_messages)), None)
    if first is None and br.evidence_thin(ranked, owner_messages):
        first = next(o for o in ranked if o.kind == bm.LEARN_FIRST)
    reason = "" if first else "No option is both clear of your limits and backed by what you said."
    final = tuple(
        dataclasses.replace(o, status="recommended") if first and o.id == first.id else o
        for o in ranked
    )
    return bm.OptionSet(
        options=final,
        recommended_id=first.id if first else None,
        no_recommendation_reason=reason,
    )


def issues(blueprint: dict[str, Any]) -> list[str]:
    """What is wrong with a stored blueprint: a step with no problem, a promise, a price, or a
    guessed cause stated as fact."""
    found: list[str] = []
    for n in blueprint.get("unlinked_steps") or []:
        found.append(f"blueprint step {n} answers no problem the owner stated (unlinked)")
    texts = [str(s.get("text") or "") for s in blueprint.get("steps") or []]
    texts += [str(r.get("text") or "") for r in blueprint.get("risks") or []]
    texts += [str(t) for t in (blueprint.get("recommendation") or {}).get("trade_offs") or []]
    for t in texts:
        if bt.promise_in(t):
            found.append(f"blueprint text promises an outcome: {t[:40]}")
        if bt.money_in(t):
            found.append(f"blueprint text holds a price or saving: {t[:40]}")
    for p in blueprint.get("problems") or []:
        cause = p.get("cause") or {}
        if cause and not cause.get("owner_stated") and cause.get("label") != HYPOTHESIS:
            found.append(f"cause of {p.get('ref')} is a guess but is not labelled as one")
    return found
