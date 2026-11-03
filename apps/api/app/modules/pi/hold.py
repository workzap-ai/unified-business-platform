"""Platform spec v1.4, 11.1 S_HOLD (G46, RT48): after a heavy disclosure or distress, no ideas and
no offer. Entered live in brain mode with `thinking` on; before this the state existed but nothing
entered it.

Entry (`next_state`): the owner's message is heavy, that is a sensitive subject the dials read as a
jump (cash trouble, debt, staff theft, family, said first, with a feeling or at length), or strong
distress or anger. An owner who in the same message asks for ideas is not held: their ask is
answered under the free-idea rules (CLAUDE.md non-negotiables), and the hold waits for the next
message. Exit: the first message that is not heavy puts the chat back to listening.

While held, the solution context is removed from the turn (`clear_solutions`), the offer is closed
by `flow.NO_OFFER`, and a reply that still carries ideas or a chain of questions is rewritten
(`reply_problem`). Pure functions; the caller moves the state.
"""

import re
from typing import Any

from app.modules.pi import dials, flow, solution_rules

# Strong distress or anger (RT48: "distressed or angry"). Mild strain ("tired", "pareshan") is not
# here: the dials and the move choice already slow down for it.
DISTRESS = dials._words(
    "can't take it|cant take it|can't go on|cant go on|i give up|i'm giving up|"
    "want to give up|hopeless|helpless|"
    "desperate|breaking down|breaking point|sleepless|furious|livid|fed up with everything|"
    "i'm done|im done|want to quit|cannot cope|can't cope",
    "haar gaya|haar gayi|haar maan li|bohat bura haal|bura haal|sab khatam|sab khatam ho gaya|"
    "tang aa gaya hoon|tang aa gayi hoon|mujhe bohat gussa|main bohat gussa|dil toot gaya|mayoos|"
    "umeed nahi|neend nahi aati|rona aa raha",
)

HELD_NOTE = (
    "The owner shared something heavy or is distressed. Acknowledge it in one plain sentence in "
    "their terms, be brief and kind, give no ideas, no product, no offer and no document, and ask "
    "at most one gentle question (or none)."
)
CLEARED = (
    "solution_asked",
    "solution_ideas",
    "solution_howto",
    "solution_asked_no_ideas",
    "solution_next",
    "solution_not_tried",
    "solution_followup",
    "solution_why",
    "open_ask",
)
# States an owner may be put on hold from: where pi listens or thinks. The offer, the documents,
# the quote and the exception states keep their own rules.
HOLDABLE = flow.LISTENING | {flow.State.S_LISTEN_THINK, flow.State.S_MAP_SHARE, flow.State.S_RETURN}


def heavy(text: str, *, first_message: bool = False) -> bool:
    """A heavy disclosure or distress (G46)."""
    text = text or ""
    if DISTRESS.search(text):
        return True
    signals = dials.read_signals(text, first_message=first_message)
    return "sensitive" in signals.reasons and signals.jump


def next_state(
    state: flow.State | None,
    said: str,
    *,
    first_message: bool = False,
    asked_for_ideas: bool = False,
) -> flow.State | None:
    """The state to move to before this reply, or None to stay."""
    if state is None:
        return None
    is_heavy = heavy(said, first_message=first_message)
    if state == flow.State.S_HOLD:
        return None if is_heavy else flow.State.S1_LISTENING
    if (
        is_heavy
        and not asked_for_ideas
        and state in HOLDABLE
        and flow.path(state, flow.State.S_HOLD) is not None  # S0 goes through S1
    ):
        return flow.State.S_HOLD
    return None


def held(context: dict[str, Any]) -> bool:
    return str((context.get("flow") or {}).get("state") or "") == flow.State.S_HOLD.value


def clear_solutions(context: dict[str, Any]) -> dict[str, Any]:
    """The context of a held turn: nothing in it hands the model an idea or a reason to give one."""
    if not held(context):
        return context
    for key in CLEARED:
        context.pop(key, None)
    context["hold_note"] = HELD_NOTE
    return context


QUESTION_MARKS = re.compile(r"[?؟]")


def reply_problem(reply: str) -> str | None:
    """Why a reply sent while held is not allowed (ideas, or more than one question), or None."""
    if solution_rules.count_ideas(reply) >= 1:
        return (
            "the owner shared something heavy: give no ideas now, acknowledge it in one plain "
            "sentence and let them lead"
        )
    if len(QUESTION_MARKS.findall(reply)) > 1:
        return "the owner shared something heavy: no chain of questions, at most one gentle one"
    return None
