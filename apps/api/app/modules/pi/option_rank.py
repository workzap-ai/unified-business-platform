"""PS-flow: ONE deterministic ranking (L2-3 `rank_options`) for the chat and for the document.

The chat ranks the ideas that survived the relevance and constraint verdicts; the document ranks
the Solution Box, the idea the chat already recommended and `learn_first`. Both build their options
here, so the same rules order them: a violator last, a rejected option last of all, an idea the gate
could not check after one it could, then effort, reversibility, owner evidence, and finally the
order the engine gave (the id), never the wording.

Pure. No model, no database, no score.
"""

import dataclasses
from collections.abc import Sequence

from app.modules.pi import blueprint_models as bm
from app.modules.pi import blueprint_rules as br

OK, UNKNOWN, VIOLATES = "ok", "unknown", "violates"


def idea_option(
    n: int,
    text: str,
    check: str,
    reason: str = "",
    *,
    addresses: Sequence[str] = (),
    evidence: Sequence[bm.Evidence] = (),
    prefix: str = "I",
) -> bm.Option:
    """An owner idea as an L2-3 option. `check` is the gate's word for it: ok, unknown, violates."""
    return bm.Option(
        id=f"{prefix}{n:02d}",
        kind="owner_action",
        what=text,
        addresses=tuple(addresses),
        benefit="",
        effort="small",  # a listed idea is something the owner can do alone
        reversibility="reversible",
        status="rejected" if check == VIOLATES else "alternative",
        evidence=tuple(evidence),
        constraint_checks=(bm.ConstraintCheck("stated limits", check, reason),),
        rejected_because=reason if check == VIOLATES else "",
    )


def rank_ideas(items: Sequence[tuple[str, str]]) -> list[int]:
    """The positions of the ideas (text, gate check) in the order to show them. Deterministic; an
    idea the gate checked ok comes before one it could not check; the engine's order breaks ties."""
    options = [idea_option(i, text, check) for i, (text, check) in enumerate(items)]
    ranked = br.rank_options(options)
    return [int(o.id[1:]) for o in ranked]


def recommended_text(items: Sequence[tuple[str, str]]) -> str:
    """The idea to start with: the first ranked one the gate found clear, else the first ranked."""
    order = rank_ideas(items)
    for i in order:
        if items[i][1] == OK:
            return items[i][0]
    return items[order[0]][0] if order else ""


def marked(option: bm.Option, status: str) -> bm.Option:
    return dataclasses.replace(option, status=status)
