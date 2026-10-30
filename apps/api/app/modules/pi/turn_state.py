"""Where the live state of a turn is decided before the model writes (spec 17.3 and 11.1).

`enter` runs once per owner message in brain mode with `thinking` on. It (1) puts the chat on hold
after a heavy disclosure or distress and takes it off again (`hold`), and (2) moves the active-topic
pointer (`topics`): a second business is parked and acknowledged, the owner steers, and pi goes back
when asked. It changes `conversation.flow_state` and `conversation.service_brief["topics"]` (no
migration) and puts the instructions for the model into the context (`topic_note`, `hold_note`).
`guard` is the reply check that goes with it (G10 for plans, 17.3, S_HOLD).

Workspaces without `thinking` never reach this module.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from app.modules.pi import feasibility, flow, hold, solution_ask, solution_rules, topics


def _walk(conversation: Any, state: flow.State, target: flow.State) -> flow.State:
    steps = flow.path(state, target) or []
    for step in steps:
        state = flow.advance(state, step)
    if steps:
        conversation.flow_state = state.value
        conversation.flow_state_since = datetime.now(UTC)
    return state


def enter(
    conversation: Any,
    state: flow.State,
    said: str,
    owner_before: Sequence[str],
    context: dict[str, Any],
) -> flow.State:
    """The state for this turn; `context` gains the topic and hold notes. `owner_before`: the
    owner's earlier messages, oldest first."""
    said = said or ""
    target = hold.next_state(
        state,
        said,
        first_message=not owner_before,
        asked_for_ideas=solution_ask.asked_for_ideas(said),
    )
    if target is not None:
        state = _walk(conversation, state, target)
    brief = dict(conversation.service_brief or {})
    before = topics.from_brief(brief)
    after, event = topics.observe(before, said, list(owner_before))
    if after.to_dict() != before.to_dict():
        conversation.service_brief = {**brief, "topics": after.to_dict()}
    if after.items:
        context["topic_active"] = after.active
        context["topics"] = [dict(i) for i in after.items]
    if event.kind != "none":
        context["topic_event"] = event.kind
        if text := topics.note(event, after):
            context["topic_note"] = text
    return state


def guard(reply: str, context: dict[str, Any]) -> str | None:
    """Why this reply cannot go out (one rewrite reason), or None. Order: held owner, topic switch,
    feasibility of a plan or idea (G10)."""
    if hold.held(context) and (why := hold.reply_problem(reply)):
        return why
    kind = str(context.get("topic_event") or "")
    if kind:
        event = topics.Event(kind=kind)
        said = str(context.get("latest_customer_message") or "")
        if why := topics.reply_problem(
            event,
            reply,
            solution_rules.count_ideas(reply),
            solution_ask.asked_for_ideas(said),
        ):
            return why
    owner = " ".join(
        [
            *(
                str(h.get("text") or "")
                for h in context.get("history") or []
                if h.get("role") == "customer"
            ),
            str(context.get("latest_customer_message") or ""),
        ]
    )
    return feasibility.reply_problem(reply, owner)
