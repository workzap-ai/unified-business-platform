"""The Solution Box document as the platform spec's eight sections (Book 5, 5.2, 5.5 to 5.7).

Only used when `response_rules.pi_mode = "brain"` and `response_rules.brain.box_offer` is true (see
`brain_docs.draft_offer`); every other workspace keeps the six-section document it always had.

The sections are built here in code wherever the spec lets code do it, so a model can never invent
them: 1 the problem list in the owner's words (map), 2 clusters with the owner's own numbers, the
likely links (at or above the 0.75 link floor) and the hypotheses the model proposes, labelled as
hypotheses; 3 two ideas per problem (the value-line check); 4 what Workzap would build, in phases,
each worded from the approved catalogue (`solutions.CATALOGUE`) and nothing else; 5 the order of
work from the owner's ranking and the "blocks" links; 6 what we need from the owner; 7 assumptions
and open questions (every detail the owner has not confirmed is listed, never hidden); 8 the quote
by phase, which a Workzap reviewer prices. pi never prices.

Pure functions over plain dicts, so the rules are testable without a database.
"""

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from app.modules.pi import box, box_signals, solutions, taxonomy

CATALOGUE_KEYS = tuple(solutions.CATALOGUE)
MAX_PHASE = 4
SECTION_COUNT = 8

# Section 2 labels every hypothesis as one (spec 5.2): the PDF prints this label before the text.
HYPOTHESIS_LABEL = {"en": "Our guess", "roman_ur": "Hamara andaza"}
NAYA_LABEL = {"en": "New", "roman_ur": "Naya"}


def document_enabled(response_rules: dict[str, Any] | None) -> bool:
    """The eight-section box is drafted only in brain mode with `brain.box_offer` exactly true, the
    same switch as the offer (read from the settings, not through `box.box_offer_enabled`)."""
    rules = response_rules or {}
    return rules.get("pi_mode") == "brain" and (rules.get("brain") or {}).get("box_offer") is True


def problem_view(
    problem: Any, ref: str, *, title: str | None = None, quotes: list[str] | None = None
) -> dict[str, Any]:
    """The facts of one problem record that the box sections use."""
    scope = problem.scope or {}
    where = ", ".join(scope.get("where") or []) or scope.get("of_total") or ""
    return {
        "ref": ref,
        "id": str(problem.id),
        "title": title or problem.title,
        "category": problem.category,
        "quotes": list(quotes if quotes is not None else (problem.user_words or [])[:2]),
        "where": str(where),
        "how_often": str((problem.frequency or {}).get("text") or ""),
        "since": str((problem.since or {}).get("text") or ""),
        "of_total": str(scope.get("of_total") or ""),
        "money": str((problem.impact or {}).get("money_text") or ""),
        "impact": list((problem.impact or {}).get("types") or []),
        "cause": str(problem.person_believes_cause or ""),
        "rank": box_signals.rank_of(problem.tags),
        **requirement_view(problem),
    }


def _loaded(problem: Any, name: str) -> Any:
    """A value that is already loaded on the row. The four B2a columns are deferred: an async
    session cannot lazy-load them, so an unloaded one reads as not said (the caller loads them)."""
    return getattr(problem, "__dict__", {}).get(name)


def requirement_view(problem: Any) -> dict[str, Any]:
    """The stored B2a fields of one problem, as plain data for the blueprint: the owner's limits,
    what they tried, the cause with its status (pi's guess stays `pi_inferred`) and the outcome
    they want. A row from before the columns existed reads as empty."""
    stated = _loaded(problem, "constraints")
    stated = stated if isinstance(stated, dict) else {}

    def text(entry: Any) -> str:
        return str(entry.get("text") or "") if isinstance(entry, dict) else str(entry or "")

    limits = {k: text(stated.get(k)) for k in ("budget", "staff", "deadline")}
    cannot = [text(e) for e in stated.get("cannot_change") or [] if text(e).strip()]
    tried = [
        {"what": str(t.get("what") or ""), "outcome": str(t.get("outcome") or "")}
        for t in (_loaded(problem, "tried") or [])
        if isinstance(t, dict) and str(t.get("what") or "").strip()
    ]
    cause = _loaded(problem, "cause")
    cause = cause if isinstance(cause, dict) else {}
    return {
        "limits": {k: v for k, v in limits.items() if v.strip()},
        "cannot_change": cannot,
        "tried": tried,
        "cause_text": str(cause.get("text") or ""),
        "cause_status": str(cause.get("status") or "") if cause.get("text") else "",
        "expected_outcome": str(_loaded(problem, "expected_outcome") or ""),
        "msgs": [str(m) for m in (_loaded(problem, "source_message_ids") or [])],
        "cause_raw": cause if cause.get("text") else None,
    }


def catalogue_text(key: str, language: str, sector: str | None) -> tuple[str, str]:
    """(English, the person's language) wording of one catalogue build. The catalogue has English
    and Roman Urdu; in any other language the local text is left empty and a reviewer translates
    it (R-DOC-07 keeps an English copy anyway)."""
    english = solutions.build_phrase(key, "en", sector)
    local = solutions.build_phrase(key, "roman_ur", sector) if language == "roman_ur" else ""
    return english, local


# --- section 2 ----------------------------------------------------------------------------------


def happening_line(view: dict[str, Any]) -> str:
    """What is happening for one problem, with only what the owner said (no guess)."""
    bits = [
        ("Where", view["where"]),
        ("How often", view["how_often"]),
        ("Since", view["since"]),
        ("What it costs them, in their words", view["money"]),
    ]
    return " | ".join(f"{name}: {value}" for name, value in bits if value)


def shown_links(links: Iterable[dict[str, Any]], titles: dict[str, str]) -> list[str]:
    """The likely links the owner may be told about: never a rejected one, and a link pi inferred
    only at or above the 0.75 link floor (spec 4.4). Worded as an observation, never a diagnosis."""
    out: list[str] = []
    floor = taxonomy.LINK_SHOWN_AT
    for link in links:
        if link.get("status") == "rejected":
            continue
        sure = link.get("evidence") in ("owner_said", "confirmed") or (
            Decimal(str(link.get("confidence", 0))) >= floor
        )
        a, b = titles.get(str(link.get("from"))), titles.get(str(link.get("to")))
        if not (sure and a and b and a != b):
            continue
        out.append(f"{a} and {b} look connected.")
    return out


def clusters(
    views: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
    *,
    language: str = "en",
    renamed: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Problems grouped by category (the owner's own groups win), best ranked group first. Each
    carries the owner's numbers and the hypotheses the model proposed for its problems."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for view in views:
        groups.setdefault(view["category"], []).append(view)

    def best(item: tuple[str, list[dict[str, Any]]]) -> tuple[int, int]:
        ranks = [v["rank"] for v in item[1] if v["rank"] is not None]
        return (min(ranks) if ranks else 99, views.index(item[1][0]))

    out: list[dict[str, Any]] = []
    for category, members in sorted(groups.items(), key=best):
        refs = [m["ref"] for m in members]
        out.append(
            {
                "name": (renamed or {}).get(category) or taxonomy.label(category, language),
                "problems": refs,
                "happening": [
                    {"ref": m["ref"], "title": m["title"], "line": happening_line(m)}
                    for m in members
                ],
                "hypotheses": [
                    str(h.get("text") or h.get("local") or "")
                    for h in hypotheses
                    if set(h.get("refs") or []) & set(refs) and (h.get("text") or h.get("local"))
                ],
            }
        )
    return out


# --- section 5 ----------------------------------------------------------------------------------


def order_of_work(
    views: list[dict[str, Any]], links: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The order the work would follow: the owner's ranking first (unranked ones keep their order
    after), then any problem that "blocks" another is moved ahead of it. A `blocks` link from A to
    B means A has to be dealt with before B (the map treats the "from" end as the root). Cycles are
    left in ranking order."""
    ranked = sorted(
        range(len(views)),
        key=lambda i: (views[i]["rank"] if views[i]["rank"] is not None else 99, i),
    )
    order = [views[i] for i in ranked]
    by_id = {v["id"]: v for v in views}
    blockers: dict[str, list[str]] = {}
    for link in links:
        if link.get("type") != "blocks" or link.get("status") == "rejected":
            continue
        a, b = str(link.get("from")), str(link.get("to"))
        if a in by_id and b in by_id and a != b:
            blockers.setdefault(b, []).append(a)
    result: list[dict[str, Any]] = []
    placed: set[str] = set()
    visiting: set[str] = set()

    def place(view: dict[str, Any]) -> None:
        if view["id"] in placed or view["id"] in visiting:
            return
        visiting.add(view["id"])
        for blocker in blockers.get(view["id"], []):
            place(by_id[blocker])
        visiting.discard(view["id"])
        if view["id"] not in placed:
            placed.add(view["id"])
            result.append(view)

    for view in order:
        place(view)
    steps: list[dict[str, Any]] = []
    for view in result:
        waiting = [by_id[a]["title"] for a in blockers.get(view["id"], []) if a in by_id]
        if view["rank"] is not None:
            why = f"You ranked this number {view['rank']}."
        else:
            why = "You did not rank this one, so it follows the ranked ones."
        if waiting:
            why = f"It comes after {', '.join(waiting)}, which has to be dealt with first."
        steps.append({"ref": view["ref"], "title": view["title"], "why": why})
    return steps


# --- section 7 ----------------------------------------------------------------------------------


def unconfirmed(views: list[dict[str, Any]], model_lines: list[str]) -> list[str]:
    """Assumptions and open questions: what the model flagged, plus every detail of a problem the
    owner has not given (5.5: "flags unconfirmed items")."""
    out = [t for t in model_lines if t.strip()]
    for view in views:
        missing = [
            name
            for name, value in (
                ("where", view["where"]),
                ("how often", view["how_often"]),
                ("since when", view["since"]),
                ("what it costs them", view["money"] or view["impact"]),
                ("what they think the cause is", view["cause"]),
            )
            if not value
        ]
        if missing:
            out.append(f"{view['title']}: not yet confirmed with you: {', '.join(missing)}.")
    return out


# --- section 4 and 8: phases ---------------------------------------------------------------------


def phase_table(
    components: list[dict[str, Any]], names: dict[int, str] | None = None
) -> list[dict[str, Any]]:
    """The phases that hold components, numbered from 1, each with a name. A phase number the
    model skipped is closed up, so the document shows phases 1, 2, 3 and never 1, 3."""
    used = sorted({int(c.get("phase") or 1) for c in components})
    return [
        {"phase": n, "name": (names or {}).get(old) or f"Phase {n}"}
        for n, old in enumerate(used, start=1)
    ]


def renumber(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    used = sorted({int(c.get("phase") or 1) for c in components})
    new = {old: n for n, old in enumerate(used, start=1)}
    return [{**c, "phase": new[int(c.get("phase") or 1)]} for c in components]


def quote_phases(solution: dict[str, Any]) -> list[dict[str, Any]]:
    """The quote's skeleton by phase: what each phase includes, with the price left empty for the
    reviewer (R-QUOTE-01)."""
    phases = solution.get("phases") or []
    components = solution.get("components") or []
    return [
        {
            "phase": p["phase"],
            "name": p.get("name") or f"Phase {p['phase']}",
            "items": [c["text"] for c in components if int(c.get("phase") or 1) == p["phase"]],
            "price": None,
        }
        for p in phases
    ]


def phase_price_issues(content: dict[str, Any], total: Decimal | None) -> list[str]:
    """A quote by phase (8): every phase has a price from the reviewer and the prices add up."""
    phases = content.get("phases") or []
    if not phases:
        return []
    issues: list[str] = []
    prices: list[Decimal] = []
    for phase in phases:
        try:
            price = Decimal(str(phase.get("price")))
        except Exception:
            price = Decimal(-1)
        if not price.is_finite() or price <= 0:
            issues.append(f"enter the price of {phase.get('name') or phase.get('phase')}")
        else:
            prices.append(price)
    if not issues and total is not None and sum(prices, Decimal(0)) != total:
        issues.append("the phase prices must add up to the total")
    return issues


# --- checks ---------------------------------------------------------------------------------------


def ideas_by_problem(content: dict[str, Any]) -> dict[str, list[str]]:
    return {
        str(entry.get("title") or entry.get("ref")): [str(i) for i in entry.get("ideas") or []]
        for entry in content.get("ideas") or []
    }


def structure_issues(content: dict[str, Any]) -> list[str]:
    """What is wrong with the box beyond the six-section rules: section 3 passes the value line,
    section 4 is catalogue only and in phases, every problem is in a cluster and in the order."""
    issues: list[str] = []
    problems = content.get("problems") or []
    refs = {str(p.get("ref")) for p in problems}
    ideas = content.get("ideas") or []
    have = {str(e.get("ref")) for e in ideas}
    for ref in sorted(refs - have):
        issues.append(f"problem {ref} has no ideas in section 3 (5.7 valueLine)")
    ok, why = box.value_line(ideas_by_problem(content))
    if not ok:
        issues.extend(f"section 3: {r}" for r in why)
    for component in content.get("components") or []:
        key = str(component.get("key") or "")
        if key not in solutions.CATALOGUE:
            issues.append(
                f'component "{str(component.get("text"))[:40]}" is not from the approved '
                "catalogue (5.7 catalogue)"
            )
            continue
        if not 1 <= int(component.get("phase") or 0) <= MAX_PHASE:
            issues.append(f"component {key} has no phase from 1 to {MAX_PHASE}")
    clustered = {r for c in content.get("clusters") or [] for r in c.get("problems") or []}
    for ref in sorted(refs - clustered):
        issues.append(f"problem {ref} is in no cluster (section 2)")
    ordered = {str(o.get("ref")) for o in content.get("order") or []}
    for ref in sorted(refs - ordered):
        issues.append(f"problem {ref} is not in the order of work (section 5)")
    if content.get("components") and not content.get("phases"):
        issues.append("section 4 has no phases")
    return issues


def new_since_sent(old_refs: Iterable[str], current: list[dict[str, Any]]) -> list[str]:
    """The titles of the problems that are not in the box that was sent: the "Naya:" list of
    Box v2 (5.6). Short, in the order they were noted."""
    known = set(old_refs)
    return [str(p["title"]) for p in current if str(p.get("ref")) not in known and p.get("title")]


def naya_line(titles: list[str], language: str = "en") -> str:
    """ "Naya: A; B": the short difference list that goes with the Box v2 offer."""
    label = NAYA_LABEL["roman_ur" if language == "roman_ur" else "en"]
    shown = [t.strip().rstrip(".") for t in titles if t.strip()][:4]
    more = len(titles) - len(shown)
    tail = f" (+{more})" if more > 0 else ""
    return f"{label}: {'; '.join(shown)}{tail}" if shown else ""
