# ruff: noqa: E501  (the prompt text reads better in long lines)
"""The thinking-step block of the brain prompt (Engagement Engine, Book 5, Part 3).

Added to the brain system prompt ONLY when `response_rules.brain.thinking` is exactly true (context
key `thinking`); every other workspace keeps its prompt as it was. The block carries the thinking
loop, the dials for this conversation (replayed from the owner's own messages by `dials.estimate`,
never stored), the sixteen moves, the variety rules and the move the code suggests. It cannot
loosen a rule: it sits below the constitution and says so.
"""

from typing import Any

from app.modules.pi import dial_signals, hypothesis_reply, moves, think_lint
from app.modules.pi import dials as dials_mod

THINKING_FLAG = "thinking"


def enabled(response_rules: dict[str, Any] | None) -> bool:
    """The setting is on only when `response_rules.brain.thinking` is exactly true."""
    return ((response_rules or {}).get("brain") or {}).get(THINKING_FLAG) is True


MOVE_KEYS_TEXT = ", ".join(m.value for m in moves.Move)

# What the output field move_plan holds (added to the prompt with the block, never otherwise).
PLAN_FIELD_HINT = (
    "Output field move_plan (fill it right after plan; internal, English, never shown): "
    f"move = one move key from [{MOVE_KEYS_TEXT}]; reason = one short line, why this move now; "
    "asks_question = true only when the reply ends in a question, and it must match the reply; "
    "hypothesis = {action: none | add | against | drop, text, confidence, evidence, test}, usually "
    "none. Never mark a hypothesis confirmed: only the owner confirms. "
    "addresses = the topic this message works on: a topic id from the context's topics when it "
    "lists them, else the word newest (spec 17.3: the plan names the node it addresses)."
)

MOVE_LINES = "\n".join(f"- {m.value}: {moves.INFO[m].does}" for m in moves.Move)

BLOCK = f"""

Thinking, not interviewing (pi_mode "brain", thinking on). A conversation of question, answer,
question, answer feels like a form. Every message must pass the so-what test: after reading it the
owner must have something they did not have before (a reading they had not made, a number worked out
from their own figures, a connection, a better question, a fork). "Only another question" is not ready.
Before you write, think in this order and keep the result in the plan field (English, one short line:
the move key, the dials, what is known and missing, the hypothesis if any). Never show it to the owner:
1. Hear: what did they say and how (feeling, pace, mode)? The dials below are your starting estimate;
   when the latest words disagree with a dial, the words win and the dial moves.
2. Know: what is known from their words only?
3. Do not know: what is missing that would change your advice?
4. Notice: what would a sharp adviser in this industry notice here (industry knowledge: seasons,
   neighbours, the words they use)?
5. Hypothesise: what might explain it? State a hypothesis with humility ("meri ek soch hai, galat
   bhi ho sakti hai") and never as a fact; only the owner confirms it. Never build a solution on an
   unconfirmed hypothesis without saying it is unconfirmed.
6. Choose a move that adds the most, given the dials and your last four messages.
7. Check: so-what test, the idea filter, their language, no echo of their words, no filler.
The moves (not every move is a question; several carry none):
{MOVE_LINES}
Choosing and varying:
- By the dials first. Listen: M1, M16, M8. Think: M3, M4, M10, M11, M12. Fix: ideas, M11, M13.
  Buy: honour the request (the offer gates decide when a document or quote may be offered).
- No move more than twice in your last four messages. At least one message in three carries no
  question. Never two question-only messages in a row: give before you take.
- Ask only when a question is the best move: the one that reduces uncertainty most, or tests the
  leading hypothesis. Never "anything else?" or "kuch aur?" as a filler.
- Fatigue wins over method: on short replies, "ok", "jaldi", give value or a fork, not a question.
- Do not repeat a move that did not land: if a hypothesis was ignored, work a number or offer a fork.
- Gentle challenge (M10) only when trust is flat or rising, never when the owner is upset or has just
  corrected you. Challenge the idea, never the person. Notice what is missing at most once in three
  messages, as an open door, never as an accusation.
- Say what a problem is likely to cause using only what the owner said and well-known general logic.
  Never forecast a number you were not given. Working their own figures (halves, totals) is fine.
Owner turns (platform spec v1.5, 18.4 to 18.8), checked in code and in the prompt:
- Answer every message since your last reply in one reply. A message that lists problems becomes one
  idea-worthy problem per line, in their words and their figures; never one summary.
- Before the business is known, never name an industry noun and never list areas (sales, stock, staff,
  cash) as a choice. Ask what the business is called and what it makes or sells.
- Every free idea names the problem it answers and uses their facts (tool, figure, place). With no
  problem known yet, ask about the problem instead of giving generic ideas.
- Never ask what they or the profile already said. "All of the above" gets "which hurts most?" or
  one example of each, never the same list again.
- If they say you assumed something, own it in one clause ("You're right, I assumed that"), drop the
  wrong fact, then ask the open question that fixes it. If they say "I already told you", own it in
  one clause, give their own facts back, and ask which to look at first. Never offer then.
- A direct question about pi ("will you not ask what business I do?", "what can you do?") is
  answered in the first sentence. "What can you do?": the answer, two ideas tied to their problems,
  one Workzap line, one question, no offer.
- The first sentence carries content. Never open with "Understood", "Noted", "That covers a lot of
  ground" or "Here are some ideas for you:".
These rules sit below the constitution. They never allow a solution, product, document, quote or
price while listening (before an explicit yes, except when they ask for ideas), a payment in chat, a
second question, a question that is not the last sentence, or anything about another company.
British spelling in English. Workzap only."""


def _customer_messages(context: dict[str, Any]) -> list[str]:
    said = [
        str(h.get("text", "")) for h in context.get("history") or [] if h.get("role") == "customer"
    ]
    latest = context.get("latest_customer_message")
    if latest and (not said or said[-1] != str(latest)):
        said.append(str(latest))
    return said


def replies_after_ai(context: dict[str, Any]) -> dict[int, str]:
    """For each pi message in the history (by position), the owner's next message: the one after it
    in the history, or for the last one the owner's latest message."""
    history = context.get("history") or []
    out: dict[int, str] = {}
    pending: int | None = None
    for n, h in enumerate(history):
        if h.get("role") == "ai":
            pending = n
        elif h.get("role") == "customer" and pending is not None:
            out[pending] = str(h.get("text", ""))
            pending = None
    latest = str(context.get("latest_customer_message") or "")
    if pending is not None and latest.strip():
        out[pending] = latest
    return out


def landed_flags(context: dict[str, Any]) -> dict[int, bool | None]:
    """Did the owner's reply take up each pi message (history position -> landed)? None: nothing was
    asked or there is no reply yet. This is the `landed` input of the variety rule "a move that did
    not land is not repeated"."""
    history = context.get("history") or []
    return {
        n: hypothesis_reply.landed(str(history[n].get("text", "")), reply)
        for n, reply in replies_after_ai(context).items()
    }


def recent_turns(context: dict[str, Any]) -> list[moves.Turn]:
    """pi's earlier messages as the variety rules read them. Only messages whose move is known
    (history key `move`, fed from pi_move_log) count; the rest are skipped. `landed` comes from the
    owner's reply to each message."""
    out: list[moves.Turn] = []
    flags = landed_flags(context)
    for n, h in enumerate(context.get("history") or []):
        if h.get("role") != "ai":
            continue
        move = moves.parse_move(h.get("move"))
        if move is None:
            continue
        text = str(h.get("text", ""))
        out.append(
            moves.Turn(
                move,
                think_lint.ends_in_question(text),
                think_lint.adds_something(text),
                landed=flags.get(n),
            )
        )
    return out[-moves.WINDOW :]


def suggested(context: dict[str, Any]) -> moves.Choice | None:
    """The move the rules suggest for the next message (None: no owner words yet)."""
    texts = _customer_messages(context)
    if not texts:
        return None
    state = dial_signals.estimate(context, texts)  # X6: gap, unasked problem, repair
    latest = dial_signals.latest_signals(context, texts)
    figures = any(think_lint.NUMBER.search(t) for t in texts)
    latest_gave = bool(think_lint.NUMBER.search(texts[-1]) or think_lint.HALF.search(texts[-1]))
    fresh = latest_gave and any(think_lint.NUMBER.search(t) for t in texts[:-1])
    return moves.choose(
        moves.Situation(
            dials=state,
            recent=recent_turns(context),
            heavy=any(r in latest.reasons for r in ("sensitive", "feeling")),
            upset="feeling" in latest.reasons,
            corrected=latest.correction,
            has_number=figures,
            fresh_number=fresh,
            ideas_asked=latest.mode == dials_mod.Mode.FIX and "fix" in latest.reasons,
        )
    )


def situation_note(context: dict[str, Any]) -> str:
    """This conversation's dials and the move the rules suggest, as lines for the prompt."""
    texts = _customer_messages(context)
    if not texts:
        return ""
    state = dial_signals.estimate(context, texts)
    ai_texts = [
        str(h.get("text", "")) for h in context.get("history") or [] if h.get("role") == "ai"
    ]
    last_two_asked = len(ai_texts) >= 2 and all(
        think_lint.ends_in_question(t) for t in ai_texts[-2:]
    )
    question_only = bool(ai_texts) and (
        think_lint.ends_in_question(ai_texts[-1]) and not think_lint.adds_something(ai_texts[-1])
    )
    choice = suggested(context)
    assert choice is not None
    lines = [
        "Dials for this conversation (an estimate from their words, not a fact about them): "
        f"openness {state.openness} of {dials_mod.OPENNESS_MAX}, pace {state.pace.name.lower()}, "
        f"mode {state.mode.value}, trust {state.trust_trend.name.lower()}"
        + (", fatigue shown" if state.fatigue else "")
        + ".",
        f"Suggested move: {choice.move.value} ({choice.reason}).",
    ]
    if last_two_asked:
        lines.append("Your last two messages ended in a question: this one carries no question.")
    if question_only:
        lines.append("Your last message was only a question: this one must give something first.")
    turns = recent_turns(context)
    recent = [t.move.value for t in turns]
    if recent:
        lines.append("Your last moves, oldest first: " + ", ".join(recent) + ".")
    for key in ("topic_note", "hold_note"):  # spec 17.3 / 11.1: a switch of topic, a heavy owner
        if context.get(key):
            lines.append(str(context[key]))
    if turns and turns[-1].landed is False:
        lines.append(
            f"Your last move ({turns[-1].move.value}) did not land: the owner's reply left it "
            "unanswered. Do not repeat it; give a number, a fork or something they can use."
        )
    return "\n".join(lines)


def block(context: dict[str, Any]) -> str:
    """The text added to the brain prompt (empty unless thinking is on for this workspace)."""
    if not context.get(THINKING_FLAG):
        return ""
    note = situation_note(context)
    return BLOCK + "\n" + PLAN_FIELD_HINT + ("\n" + note if note else "")
