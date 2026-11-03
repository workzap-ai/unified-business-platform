"""Live test 5 (owner, tuition academy, fee late): every noted fact counts for the fit, the Workzap
line for fee reminders is concrete outside the shop sectors, and the board caption is plain."""

from app.modules.pi import brain_visuals, problem_extract, solution_ideas, solutions


def test_the_caption_is_one_short_plain_line() -> None:
    for lang in ("en", "roman_ur"):
        caption = brain_visuals.TEXT[lang]["caption"]
        assert caption.endswith(".") and len(caption.split()) <= 6
    assert "tasveer" not in brain_visuals.TEXT["roman_ur"]["caption"]


def test_the_extractor_keeps_a_reason_the_problem_hurts_and_roman_script() -> None:
    assert "parents" in problem_extract.SYSTEM and "second problem" in problem_extract.SYSTEM
    assert "Roman Urdu stays in Roman letters" in problem_extract.SYSTEM


def test_all_noted_facts_decide_which_fee_entry_fits() -> None:
    entries = solutions.load("tuition_centres_and_academies")["problems"]  # type: ignore[index]
    alone = "Fee late"
    everything = (
        f"{alone} call se parents ko bura lagta hai pehle hafte mein lete hain fees WhatsApp"
    )
    fees = next(e for e in entries if e["id"] == "p2_receivables_late")
    other = next(e for e in entries if e["id"] == "p1_cash_mismatch")
    assert solution_ideas.fit(fees, everything) > solution_ideas.fit(other, everything)
