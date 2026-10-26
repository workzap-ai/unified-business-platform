# ruff: noqa: E501  (the prompt text reads better in long lines)
"""The thinking-step block of the brain prompt (Engagement Engine, Book 5, Part 3).

Added to the brain system prompt ONLY when `response_rules.brain.thinking` is exactly true (context
key `thinking`); every other workspace keeps its prompt as it was. The block carries the thinking
loop, the dials for this conversation (replayed from the owner's own messages by `dials.estimate`,
never stored), the sixteen moves, the variety rules and the move the code suggests. It cannot
loosen a rule: it sits below the constitution and says so.
"""

from typing import Any

from app.modules.pi import dials as dials_mod
from app.modules.pi import moves, think_lint

THINKING_FLAG = "thinking"


def enabled(response_rules: dict[str, Any] | None) -> bool:
    """The setting is on only when `response_rules.brain.thinking` is exactly true."""
    return ((response_rules or {}).get("brain") or {}).get(THINKING_FLAG) is True


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


def situation_note(context: dict[str, Any]) -> str:
    """This conversation's dials and the move the rules suggest, as lines for the prompt."""
    texts = _customer_messages(context)
    if not texts:
        return ""
    state = dials_mod.estimate(texts)
    latest = dials_mod.read_signals(texts[-1], first_message=len(texts) == 1)
    figures = any(think_lint.NUMBER.search(t) for t in texts)
    latest_gave = bool(think_lint.NUMBER.search(texts[-1]) or think_lint.HALF.search(texts[-1]))
    fresh = latest_gave and any(think_lint.NUMBER.search(t) for t in texts[:-1])
    ai_texts = [
        str(h.get("text", "")) for h in context.get("history") or [] if h.get("role") == "ai"
    ]
    last_two_asked = len(ai_texts) >= 2 and all(
        think_lint.ends_in_question(t) for t in ai_texts[-2:]
    )
    question_only = bool(ai_texts) and (
        think_lint.ends_in_question(ai_texts[-1]) and not think_lint.adds_something(ai_texts[-1])
    )
    choice = moves.choose(
        moves.Situation(
            dials=state,
            heavy=any(r in latest.reasons for r in ("sensitive", "feeling")),
            upset="feeling" in latest.reasons,
            corrected=latest.correction,
            has_number=figures,
            fresh_number=fresh,
            ideas_asked=latest.mode == dials_mod.Mode.FIX and "fix" in latest.reasons,
        )
    )
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
    return "\n".join(lines)


def block(context: dict[str, Any]) -> str:
    """The text added to the brain prompt (empty unless thinking is on for this workspace)."""
    if not context.get(THINKING_FLAG):
        return ""
    note = situation_note(context)
    return BLOCK + ("\n" + note if note else "")
