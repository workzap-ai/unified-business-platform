"""PS-4: a solution blueprint as plain text, in English, Roman Urdu, Urdu or Arabic.

Plain text only: no markdown, no tables, one short line per fact, ids like S1 and G2 instead of
bare numbers. The owner's words are kept as written. Labels come from `blueprint_strings`.
`render_blueprint` never raises; with a status other than ready it renders only what is missing and
the one targeted question, as the last line.
"""

from __future__ import annotations

import re
from typing import Any

from app.modules.pi import blueprint_strings as bs
from app.modules.pi.blueprint_checks import canon_number
from app.modules.pi.blueprint_types import INSUFFICIENT, READY, REFUSED, Blueprint

_MARKDOWN = re.compile(r"[|*#`~<>]|^[-=_]{3,}", re.M)
_WS = re.compile(r"[ \t\r\f\v]+")


def _line(text: Any) -> str:
    """A value as one clean line: no markdown characters, no line breaks."""
    t = _MARKDOWN.sub(" ", str(text)).replace("\n", " ")
    return _WS.sub(" ", t).strip()


def _sent(text: Any) -> str:
    """A value as a clause: one clean line without a closing full stop."""
    return _line(text).rstrip(".!?؟۔ ")


def render_blueprint(blueprint: Blueprint, language: Any = None) -> str:
    """The blueprint as plain text in `language` (default: the language it was built in)."""
    try:
        lang = bs.norm_language(language if language is not None else blueprint.language)
        return _render(blueprint, lang)
    except Exception:
        return bs.tr(bs.norm_language(language), "unreadable")


def _render(bp: Blueprint, lang: str) -> str:
    t = bs.tr
    out: list[str] = [t(lang, "title")]

    def head(key: str) -> None:
        out.append("")
        out.append(t(lang, key))

    def role(r: str) -> str:
        return t(lang, f"role_{r}") if r in ("owner", "staff", "pi", "reviewer") else r

    if bp.status != READY:
        if bp.status == REFUSED:
            head("sec_refusal")
            out += [_line(x) for x in bp.refusal]
            if bp.constraints:
                head("sec_constraints")
                out += _constraint_lines(bp, lang)
        else:
            head("sec_missing")
            out += [_line(m.text) for m in bp.missing]
        if bp.status == INSUFFICIENT and bp.next_question:
            head("sec_question")
            out.append(_line(bp.next_question))  # the last line, and the only question
        return "\n".join(out)

    out.append(t(lang, "nothing_starts"))
    head("sec_summary")
    if bp.summary:
        out.append(_line(bp.summary.text))

    head("sec_problems")
    for pr in bp.problems:
        out.append(f"{pr.id}: {_sent(pr.title)}")
        out += [f"  {t(lang, 'lbl_evidence')}: {_line(w)}" for w in pr.words]

    head("sec_facts")
    for f in bp.facts:
        who = f"{f.problem}: " if f.problem else ""
        label = t(lang, f"fact_{f.kind}")
        if f.kind == "correction":
            was, now = t(lang, "lbl_was"), t(lang, "lbl_now")
            out.append(f"{who}{label}. {was}: {_sent(f.was)}. {now}: {_sent(f.text)}")
        else:
            out.append(f"{who}{label}: {_line(f.text)}")

    head("sec_causes")
    for c in bp.causes:
        status = t(lang, f"cause_{c.status}") if c.status != "unknown" else ""
        line = f"{c.problem}: {_sent(c.text)}" + (f" ({status})" if status else "")
        out.append(line)
        out += [f"  {t(lang, 'lbl_evidence')}: {_line(w)}" for w in c.evidence]

    head("sec_reasons")
    out += [_line(r.text) for r in bp.reasons]

    head("sec_alternatives")
    for a in bp.alternatives:
        out.append(f"{a.id}: {_sent(a.what)}" if a.id else _line(a.what))
        out += [f"  {_line(x)}" for x in a.why_not.split("\n") if x.strip()]

    head("sec_architecture")
    for m in bp.modules:
        out.append(f"{m.id}: {_line(m.name)}")
        for n in m.not_changed:
            out.append(f"  {t(lang, 'lbl_not_changed')}: {_line(n)}")

    head("sec_workflow")
    for s in bp.steps:
        if s.kind in ("approval", "rollback"):
            continue
        out.append(f"{s.id}: {_line(s.text)}")
        out.append(f"  {_who_done(s, lang)}")

    head("sec_dependencies")
    if bp.edges:
        after: dict[str, list[str]] = {}
        for edge in bp.edges:
            after.setdefault(edge.after, []).append(edge.before)
        for sid, before in after.items():
            out.append(f"{sid}: {t(lang, 'lbl_after')} {', '.join(before)}")
    else:
        out.append(t(lang, "deps_none"))

    head("sec_external")
    for x in bp.external:
        flag = f" {t(lang, 'lbl_blocking')}." if x.blocking else ""
        out.append(f"{x.id}: {_sent(x.text)} ({t(lang, 'lbl_status_unknown')}).{flag}")

    head("sec_data")
    for d in bp.data:
        if d.kind == "integration":
            out.append(t(lang, "data_integration", name=_sent(d.name)))
        elif d.kind == "entity":
            out.append(t(lang, "data_entity", name=_sent(d.name)))
        else:
            out.append(_line(d.name))

    head("sec_responsibilities")
    for r in bp.responsibilities:
        out.append(f"{role(r.role)}: {', '.join(r.steps)}")
        perms = [_line(x) for x in r.permissions] or [t(lang, "perm_none")]
        out.append(f"  {t(lang, 'lbl_permissions')}: {' '.join(perms)}")

    head("sec_costs")
    for cl in bp.costs:
        if cl.amount is None:
            out.append(f"{_line(cl.item)}: {t(lang, 'costs_unknown')}")
        else:
            amount = f"{canon_number(str(cl.amount))} {cl.currency}".strip()
            out.append(f"{_line(cl.item)}: {amount} ({t(lang, 'src_staff')}: {_line(cl.source)})")

    head("sec_timeline")
    for tl in bp.timeline:
        if not tl.duration:
            out.append(f"{tl.item}: {t(lang, 'time_unknown')}")
        else:
            out.append(
                f"{tl.item}: {_line(tl.duration)} ({t(lang, 'lbl_source')}: {_line(tl.source)})"
            )

    head("sec_risks")
    out += [_line(r.text) for r in bp.risks]
    out += [_line(u) for u in bp.unknowns]

    head("sec_open")
    out += [_line(o.text) for o in bp.open_items]

    head("sec_milestones")
    for m2 in bp.milestones:
        out.append(f"{m2.id}: {_line(m2.name)}. {', '.join(m2.steps)}")

    head("sec_acceptance")
    for c2 in bp.acceptance:
        out.append(f"{c2.id}: {_line(c2.text)}")

    head("sec_success")
    for me in bp.success:
        out.append(f"{me.id}: {_line(me.what)}")
        base = (
            _line(me.baseline)
            if me.baseline
            else t(lang, "baseline_unknown", step=me.baseline_source.split(" ")[-1])
        )
        out.append(f"  {t(lang, 'lbl_baseline')}: {base}")
        out.append(f"  {t(lang, 'lbl_target')}: {_line(me.target) or t(lang, 'target_unknown')}")
        out.append(f"  {t(lang, 'lbl_measured')}: {role(me.measured_by)}")

    head("sec_rollback")
    for s in bp.steps:
        if s.kind == "rollback":
            out.append(f"{s.id}: {_line(s.text)}")
            out.append(f"  {_who_done(s, lang)}")

    head("sec_approvals")
    for s in bp.steps:
        if s.kind == "approval":
            out.append(f"{s.id}: {_line(s.text)}")
            out.append(f"  {_who_done(s, lang)}")

    head("sec_constraints")
    out += _constraint_lines(bp, lang)
    return "\n".join(out)


def _who_done(s: Any, lang: str) -> str:
    t = bs.tr
    role = t(lang, f"role_{s.role}") if s.role in ("owner", "staff", "pi", "reviewer") else s.role
    return f"{t(lang, 'lbl_who')}: {role}. {t(lang, 'lbl_done')}: {_line(s.done_check)}"


def _constraint_lines(bp: Blueprint, lang: str) -> list[str]:
    t = bs.tr
    lines = []
    for k in bp.constraints:
        label = k.label.replace("#", "_")
        verdict = t(lang, "res_" + k.result)
        lines.append(f"{label}: {_sent(k.text)}. {verdict}. {_line(k.reason)}")
    return lines
