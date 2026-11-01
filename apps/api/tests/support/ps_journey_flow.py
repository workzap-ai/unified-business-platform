# ruff: noqa: E501
"""The journeys through the pure parts of the flow: the owner's record folded from the scripted
notes, the L2-1 gate, the blueprint builder and the decision gates (no database, no model).

`tests/integration/ps_journey_harness.py` feeds the same functions with what the real pipeline
stored, so the unit and the integration tests assert the same behaviour.
"""

import json
import re
from typing import Any

from tests.support.ps_journey_checks import (
    figures_after_corrections,
    has_figure,
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
                "cause_raw": None,
                "of_total": p["where"],
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


def components(
    journey: dict[str, Any], refs: list[str], kind: str = "valid"
) -> list[dict[str, Any]]:
    """Blueprint components (the steps of the one Solution Box) from the journey's ideas:
    `valid` = the linked ideas the gate must not reject; `violating` = the ideas that break a limit;
    `generic` = the valid ones plus the unrelated idea (it names no problem)."""
    from app.modules.pi import solutions

    key = next(iter(solutions.CATALOGUE))
    pick = {
        "valid": ("not_rejected",),
        "violating": ("reject",),
        "generic": ("not_rejected", "generic"),
    }[kind]
    return [
        {
            "key": key,
            "text": idea["text"],
            "phase": 1,
            "refs": [refs[r] for r in idea["refs"] if r < len(refs)],
        }
        for idea in journey["ideas"]
        if idea["must"] in pick
    ]


def build_blueprint(
    journey: dict[str, Any],
    views: list[dict[str, Any]],
    owner_messages: dict[str, str],
    kind: str = "valid",
    chat_pick: str = "",
) -> dict[str, Any]:
    """PS-4's blueprint (blueprint_wire.build): status, localized text, issues, recommended id."""
    from app.modules.pi import blueprint_wire

    comps = components(journey, [v["ref"] for v in views], kind)
    return blueprint_wire.build(
        views,
        comps,
        ["a contact person"],
        owner_messages,
        journey["language"],
        chat_pick=chat_pick,
    )


COMPONENTS = (
    "ready_clean",
    "owner_words_kept",
    "figures",
    "script",
    "violating_not_recommended",
    "generic_flagged",
    "evidence_survives_correction",
    "deterministic",
    "rerank",
)


def blueprint_findings(
    journey: dict[str, Any],
    views: list[dict[str, Any]],
    owner_messages: dict[str, str],
) -> dict[str, list[str]]:
    """What is wrong with the blueprint for this journey, by component (empty list = fine)."""
    found: dict[str, list[str]] = {k: [] for k in COMPONENTS}
    bp = build_blueprint(journey, views, owner_messages)
    text = bp["text"]
    if bp["status"] not in ("ready", "insufficient"):
        found["ready_clean"].append(f"status {bp['status']}: {bp['refusal']}")
    if bp["status"] == "ready" and bp["issues"]:
        found["ready_clean"].append(f"issues {bp['issues']}")
    if not text.strip():
        found["ready_clean"].append("empty text")
    if bp["status"] == "ready" and bp["recommended"] == "BOX":
        quote = (views[0].get("quotes") or [""])[0]
        if quote and quote not in text:
            found["owner_words_kept"].append(f"the owner's words are not in the blueprint: {quote}")
        kept, gone = figures_after_corrections(journey)
        for fig in kept:
            if not has_figure(text, fig):
                found["figures"].append(f"kept figure {fig} missing from the blueprint text")
        for fig in gone:
            if has_figure(text, fig):
                found["figures"].append(f"corrected figure {fig} still in the blueprint text")
    if journey["language"] in NON_LATIN and not re.search(r"[؀-ۿ]", text):
        found["script"].append("the blueprint is not in the owner's script")
    if bp["status"] == "ready" and bp["recommended"] == "LEARN":
        found["evidence_survives_correction"].append(
            "learn more first although the owner described the problem clearly"
        )
    if any(i["must"] == "reject" for i in journey["ideas"]):
        bad = build_blueprint(journey, views, owner_messages, "violating")
        if bad["status"] == "ready" and bad["recommended"] == "BOX":
            found["violating_not_recommended"].append(
                "a blueprint of ideas that break the owner's limits is recommended"
            )
    if any(i["must"] == "generic" for i in journey["ideas"]):
        mixed = build_blueprint(journey, views, owner_messages, "generic")
        if mixed["status"] == "ready" and not mixed["issues"]:
            found["generic_flagged"].append("an unrelated generic step passed with no issue")
    again = build_blueprint(journey, views, owner_messages)
    if json.dumps(bp, sort_keys=True, ensure_ascii=False) != json.dumps(
        again, sort_keys=True, ensure_ascii=False
    ):
        found["deterministic"].append("two runs gave different blueprints")
    if journey["rerank"]:
        idea = journey["ideas"][journey["rerank"]["idea"]]["text"]
        picked = build_blueprint(journey, views, owner_messages, chat_pick=idea)
        if picked["recommended"] == "CHAT":
            found["rerank"].append("the idea the owner's new limit rules out is still recommended")
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


UNREADABLE_LIMIT = (
    "limits written in Urdu or Arabic are unreadable to constraint_check (L2-1-c remainder, "
    "docs/pi-saas/pi-ps-flow-open-issues.md): the idea stays 'unknown' and is shown or recommended"
)
RELEVANCE_KEEPS = (
    "FINDING PS-3 evaluate_idea keeps an unrelated idea as linked (relevance lexicon): "
    "idea_relevance.py"
)
RELEVANCE_DROPS = (
    "FINDING PS-3 evaluate_idea drops a valid idea that is worded differently from the owner "
    "(unlinked): idea_relevance.py"
)
UNLINKED_STEP = (
    "FINDING PS-4 blueprint_wire.build gives a blueprint with an unrelated step (it names no "
    "problem) status ready and no issue: blueprint_wire.py option_set / blueprint_issues"
)
BUDGET_NOT_SHOWN = (
    "FINDING the owner's budget figure is stored but is not in the blueprint text "
    "(blueprint_wire.build -> render_blueprint)"
)
CORRECTED_QUOTE = (
    "FINDING after a corrected figure the corrected quote is not in the blueprint text"
)
GENERIC_BY_ID = {
    "gym_en",
    "trucking_roman_ur",
    "crops_roman_ur",
    "pharmacy_ur",
    "rental_ur",
    "ecommerce_ar",
}
DROPPED_BY_ID = {"poultry_en", "clinic_en", "dairy_roman_ur", "poultry_ur", "dairy_ar", "crops_ar"}


def pending_components(journey: dict[str, Any]) -> dict[str, str]:
    """Components of this journey that depend on behaviour not landed yet, with the reason."""
    out: dict[str, str] = {}
    ideas = journey["ideas"]
    jid = journey["id"]
    rejects = any(i["must"] == "reject" for i in ideas)
    if journey["language"] in NON_LATIN and rejects:
        for key in ("gate_reject", "voice_violating_removed", "violating_not_recommended"):
            out[key] = UNREADABLE_LIMIT
    if jid == "clinic_roman_ur":
        out["gate_reject"] = TRIED_ROMAN
    if jid == "repair_roman_ur":
        out["voice_unknown_marked"] = MISSING_BUDGET
    if jid in GENERIC_BY_ID:
        out["voice_generic_removed"] = RELEVANCE_KEEPS
    if jid in DROPPED_BY_ID:
        out["voice_valid_kept"] = RELEVANCE_DROPS
    if any(i["must"] == "generic" for i in ideas):
        out["generic_flagged"] = UNLINKED_STEP
    budget = (journey["expect"].get("limits") or {}).get("budget", "")
    if any(f in budget for f in journey["expect"].get("kept") or []):
        out["figures"] = BUDGET_NOT_SHOWN
    if "corrections" in journey["difficulty"]:
        out["evidence_survives_correction"] = EVIDENCE_AFTER_CORRECTION
        out["owner_words_kept"] = CORRECTED_QUOTE
    if journey["rerank"] and journey["language"] in NON_LATIN:
        out["rerank"] = UNREADABLE_LIMIT
    if journey["expect"].get("tried"):
        out["reply_asks_known"] = ASKS_KNOWN
    return out


# --- the chat: PS-3 verdicts plus the L2-1 gate through option_voice.voice -----------------------

BUL = "\u2022 "
VOICE_COMPONENTS = (
    "voice_violating_removed",
    "voice_generic_removed",
    "voice_valid_kept",
    "voice_unknown_marked",
    "voice_one_question",
    "voice_pick",
)


def problem_records(journey: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"title": p["title"], "user_words": p["quotes"], "group": p["category"]}
        for p in fold_record(journey)
    ]


def voiced(
    journey: dict[str, Any],
    texts: list[str] | None = None,
    upto: int | None = None,
    reqs: Any = None,
):
    from app.modules.pi import option_voice, option_wiring

    problems = fold_record(journey, upto)
    if reqs is None:
        reqs = option_wiring.requirements_from(requirements_data(problems))
    ideas = texts if texts is not None else [i["text"] for i in journey["ideas"]]
    reply = "Here are some ideas:\n" + "\n".join(f"{BUL}{t}" for t in ideas)
    records = [
        {"title": p["title"], "user_words": p["quotes"], "group": p["category"]} for p in problems
    ]
    return option_voice.voice(reply, reqs, journey["language"], records)


def voice_findings(journey: dict[str, Any]) -> dict[str, list[str]]:
    return voice_findings_for(journey)


def voice_findings_for(journey: dict[str, Any], reqs: Any = None) -> dict[str, list[str]]:
    """The chat verdicts over the idea list; `reqs` are the stored requirements (else folded)."""
    found: dict[str, list[str]] = {k: [] for k in VOICE_COMPONENTS}
    v = voiced(journey, reqs=reqs)
    for n, idea in enumerate(journey["ideas"]):
        shown = idea["text"].rstrip(". ") in v.reply
        if idea["must"] == "reject" and shown:
            found["voice_violating_removed"].append(f"idea {n} still shown")
        if idea["must"] == "generic" and shown:
            found["voice_generic_removed"].append(f"idea {n} still shown")
        if idea["must"] == "not_rejected" and not shown:
            found["voice_valid_kept"].append(f"idea {n} left out: {idea['text'][:40]}")
    n_unknown = sum(i["must"] == "unknown" for i in journey["ideas"])
    if n_unknown and v.unknown < n_unknown:
        found["voice_unknown_marked"].append(f"{v.unknown} marked, {n_unknown} expected")
    marks = v.question.count("?") + v.question.count("\u061f")
    if v.question and (marks != 1 or not v.question.rstrip().endswith(("?", "\u061f"))):
        found["voice_one_question"].append(v.question)
    clear = [i["text"].rstrip(". ") for i in journey["ideas"] if i["must"] == "not_rejected"]
    if v.accepted and v.pick and v.pick.rstrip(". ") not in clear:
        found["voice_pick"].append(f"pick is not a valid idea: {v.pick[:50]}")
    return found


# --- the same option leads the chat and the document (real brain_docs.apply_box) -----------------

SAME_OPTION = (
    "FINDING the chat's first clear idea (brief['chat_pick']) is not the option that leads the "
    "document: the recommendation is the Solution Box or 'learn first' instead "
    "(blueprint_wire.option_set ranking, option_rank)"
)


def same_option_findings(journey: dict[str, Any]) -> list[str]:
    """The idea option_voice.voice puts first (its pick) goes to brain_docs.apply_box as
    brief['chat_pick']; the document's blueprint must recommend that same idea and print it."""
    from app.modules.pi import brain_docs as bd
    from app.modules.pi import solutions

    v = voiced(journey)
    if not v.pick:
        return ["the chat made no pick"]
    views = synthetic_views(journey)
    refs = [x["ref"] for x in views]
    key = next(iter(solutions.CATALOGUE))
    draft = bd.BoxDraft(
        components=[bd.BoxComponent(key=key, phase=1, problems=refs)],
        phases=[bd.Line(text="First", refs=refs)],
        needs=["a contact person"],
    )
    content = {
        "components": [{"key": key, "text": "x", "phase": 1, "refs": refs}],
        "needs": ["a contact person"],
    }
    out = bd.apply_box(
        content,
        draft,
        views=views,
        links=[],
        language=journey["language"],
        local=False,
        sector=None,
        owner_messages=synthetic_owner_messages(journey),
        chat_pick=v.pick,
    )
    blueprint = out["blueprint"]
    problems = []
    if not str(blueprint["recommended"]).startswith("CHAT"):
        problems.append(f"the document recommends {blueprint['recommended']}, not the chat pick")
    elif v.pick.rstrip(". ") not in blueprint["text"]:
        problems.append("the chat pick leads but its words are not in the document")
    return problems
