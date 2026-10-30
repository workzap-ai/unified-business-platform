"""Audit X6: return after a gap, an unasked problem and a good repair now reach the dials."""

from typing import Any

from app.modules.pi import box_signals, dial_signals, dials, think_prompt


def history(*rows: tuple[str, str, str]) -> list[dict[str, str]]:
    return [{"role": r, "at": at, "text": t} for r, at, t in rows]


def test_a_return_after_a_day_raises_trust() -> None:
    ctx: dict[str, Any] = {
        "history": history(
            ("customer", "2026-10-20 10:00", "stock kam hai"),
            ("ai", "2026-10-20 10:01", "Kab se hai ye?"),
            ("customer", "2026-10-20 10:05", "do hafte se"),
            ("ai", "2026-10-20 10:06", "Samajh gaya."),
        ),
        "latest_customer_message": "hi, wapas aya hoon",
        "hours_since_previous_message": 50.0,
    }
    texts = think_prompt._customer_messages(ctx)
    extra = dial_signals.extras(ctx, texts)
    assert extra[-1] == {"gap_hours": 50.0} and extra[0] == {}
    assert dial_signals.estimate(ctx, texts).trust_trend == dials.Trust.RISING
    assert dials.estimate(texts).trust_trend == dials.Trust.FLAT  # the old replay never moved


def test_a_gap_inside_the_history_counts_for_that_message() -> None:
    ctx: dict[str, Any] = {
        "history": history(
            ("customer", "2026-10-20 10:00", "stock kam hai"),
            ("ai", "2026-10-20 10:01", "Kab se?"),
            ("customer", "2026-10-22 10:00", "do din se"),
        ),
        "latest_customer_message": "do din se",
    }
    texts = think_prompt._customer_messages(ctx)
    assert texts == ["stock kam hai", "do din se"]
    assert dial_signals.extras(ctx, texts)[1]["gap_hours"] == 48.0


def test_a_problem_raised_after_a_statement_is_unasked() -> None:
    ctx: dict[str, Any] = {
        "history": history(("ai", "2026-10-20 10:00", "Welcome, I am pi, an AI.")),
        "latest_customer_message": "deliveries late ho jati hain, bohat masla hai",
    }
    texts = ["deliveries late ho jati hain, bohat masla hai"]
    assert dial_signals.extras(ctx, texts)[0] == {"unasked_problem": True}
    asked = {**ctx, "history": history(("ai", "2026-10-20 10:00", "Kya masla hai?"))}
    assert dial_signals.extras(asked, texts)[0] == {}
    assert "unasked problem" in dial_signals.latest_signals(ctx, texts).reasons


def test_a_good_repair_after_a_correction_raises_trust() -> None:
    ctx: dict[str, Any] = {
        "history": history(
            ("customer", "2026-10-20 10:00", "mera stock kam hota hai"),
            ("ai", "2026-10-20 10:01", "Aap ki sales kam hain?"),
            ("customer", "2026-10-20 10:02", "nahi aisa nahi hai, stock kam hota hai"),
            ("ai", "2026-10-20 10:03", "Theek, stock kam hota hai. Kab se?"),
        ),
        "latest_customer_message": "teen mahine se",
    }
    texts = think_prompt._customer_messages(ctx)
    extra = dial_signals.extras(ctx, texts)
    assert extra[-1] == {"repaired": True} and extra[1] == {}
    # no repair credit when pi has not answered the correction yet
    unanswered = {**ctx, "history": ctx["history"][:3]}
    assert dial_signals.extras(unanswered, think_prompt._customer_messages(unanswered))[-1] == {}


def test_the_situation_note_and_box_signals_use_the_extras() -> None:
    ctx: dict[str, Any] = {
        "thinking": True,
        "history": history(
            ("customer", "2026-10-20 10:00", "stock kam hai"),
            ("ai", "2026-10-20 10:01", "Samajh gaya."),
        ),
        "latest_customer_message": "wapas aya hoon, ab bhi stock ka masla hai",
        "hours_since_previous_message": 30.0,
    }
    assert "trust rising" in think_prompt.situation_note(ctx)
    assert box_signals.trust_and_upset(ctx)[0] == "rising"


def test_estimate_without_extras_is_unchanged() -> None:
    texts = ["stock kam hai", "ok", "ok"]
    assert dials.estimate(texts) == dials.estimate(texts, extras=None)
    assert dials.estimate(texts) == dials.estimate(texts, extras=[])
