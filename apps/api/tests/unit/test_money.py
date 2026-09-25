from decimal import Decimal

import pytest

from app.shared.errors import InvalidTransition
from app.shared.money import compute_totals, line_total, quantize, tax_for
from app.shared.state_machine import StateMachine


def test_quantize_rounds_half_up_and_refuses_float():
    assert quantize(Decimal("2.345")) == Decimal("2.35")
    assert quantize(Decimal("2.334")) == Decimal("2.33")
    assert quantize(Decimal("0.125")) == Decimal("0.13")  # banker's rounding would give 0.12
    assert quantize(Decimal("-0.125")) == Decimal("-0.13")
    with pytest.raises(TypeError):
        quantize(0.1)  # type: ignore[arg-type]


def test_compute_totals_quantizes_each_step_and_rejects_oversized_discounts():
    lines, totals = compute_totals(
        [
            (Decimal("3"), Decimal("33.35"), Decimal("0")),
            (Decimal("1.5"), Decimal("10.03"), Decimal("0.10")),
        ],
        Decimal("0.075"),
    )
    assert lines == [Decimal("100.05"), Decimal("14.95")]
    assert (totals.subtotal, totals.discount_total, totals.tax_total, totals.total) == (
        Decimal("115.10"),
        Decimal("0.10"),
        Decimal("8.63"),
        Decimal("123.63"),
    )
    assert all(isinstance(v, Decimal) for v in (*lines, totals.total))
    with pytest.raises(ValueError):
        compute_totals([(Decimal("1"), Decimal("5.00"), Decimal("5.01"))], Decimal("0"))
    _, empty = compute_totals([], Decimal("0.2"))
    assert empty.total == Decimal("0.00")


def test_line_total_never_negative_and_tax_is_rounded():
    assert line_total(2, Decimal("1.00"), Decimal("5.00")) == Decimal("0.00")
    assert tax_for(Decimal("0.05"), Decimal("0.1")) == Decimal("0.01")  # 0.005 -> 0.01


def test_state_machine_rejects_unlisted_and_unknown_states():
    machine = StateMachine("thing", {"a": frozenset({"b"}), "b": frozenset()})
    machine.ensure("a", "b")
    for current, target in (("b", "a"), ("a", "a"), ("a", "zzz"), ("zzz", "a")):
        with pytest.raises(InvalidTransition):
            machine.ensure(current, target)
    assert machine.next_states("a") == ["b"] and machine.next_states("unknown") == []
