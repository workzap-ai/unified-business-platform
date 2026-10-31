"""L2-1: the hard gate over a set of options. Pure: no database, no model, no score.

`gate_options(options, requirements, language)` runs `constraint_check.check_option` on each
option and sorts them into accepted, rejected (with the verdict that rejected them) and unknown.
A hard violation rejects the option whatever anyone thinks of its relevance: no score is an input,
so none can rescue it. Unknown is neither accepted nor rejected: it stays visible with its reason.

When no option is left (nothing accepted and nothing unknown) the result says so with a typed
`next_step`, `ASK_TARGETED_QUESTION`, and names what to ask about in `ask_about`. It never fills
a quota with options the owner said they cannot do, and it carries no text for the owner: the
caller words the one question.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.modules.pi import constraint_check as cc
from app.modules.pi.requirements_types import Requirements


class NextStep(StrEnum):
    USE_ACCEPTED = "use_accepted"  # at least one option passed every stated limit
    CHECK_UNKNOWN = "check_unknown"  # none passed; some could not be checked (show with a flag)
    ASK_TARGETED_QUESTION = "ask_targeted_question"  # none left: ask one question, do not pad


@dataclass(frozen=True, slots=True)
class Gated:
    option: str
    verdict: cc.Verdict


@dataclass(frozen=True, slots=True)
class GateResult:
    accepted: tuple[Gated, ...]
    rejected: tuple[Gated, ...]
    unknown: tuple[Gated, ...]
    next_step: NextStep
    ask_about: str | None = None  # the rule that rejected most: budget, cannot_change, tried_failed

    @property
    def accepted_options(self) -> tuple[str, ...]:
        return tuple(g.option for g in self.accepted)

    @property
    def no_option_left(self) -> bool:
        return self.next_step is NextStep.ASK_TARGETED_QUESTION


def _as_list(options: Any) -> list[Any]:
    """One string is one option; a list or iterator is its items; anything else is no options."""
    if isinstance(options, str):
        return [options]
    if isinstance(options, (bytes, bytearray, Mapping)) or options is None:
        return []
    try:
        return list(options)
    except TypeError:
        return []


def gate_options(
    options: Sequence[str],
    requirements: Requirements | None,
    language: str | None = None,
) -> GateResult:
    """Never raises. An item that is not text is `unknown` with a reason."""
    accepted: list[Gated] = []
    rejected: list[Gated] = []
    unknown: list[Gated] = []
    for option in _as_list(options):
        verdict = cc.check_option(option, requirements, language)
        bucket = {"ok": accepted, "violates": rejected, "unknown": unknown}[verdict.status]
        bucket.append(Gated(option, verdict))
    if accepted:
        step = NextStep.USE_ACCEPTED
    elif unknown:
        step = NextStep.CHECK_UNKNOWN
    else:
        step = NextStep.ASK_TARGETED_QUESTION
    about = None
    if step is NextStep.ASK_TARGETED_QUESTION and rejected:
        about = Counter(g.verdict.rule for g in rejected).most_common(1)[0][0]
    return GateResult(tuple(accepted), tuple(rejected), tuple(unknown), step, about)
