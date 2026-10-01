"""Forecast helpers: honest about thin history, sensible on clean trends."""

import pytest

from app.modules.workspace_agent.forecast import change, holt, next_months, trend_direction


def test_linear_growth_continues_with_a_range_around_it():
    result = holt([100, 120, 140, 160, 180, 200], horizon=3)
    assert result is not None and result.history_points == 6
    assert result.values[0] > 200 and result.values[0] < result.values[2]
    assert all(
        lo <= v <= hi for lo, v, hi in zip(result.low, result.values, result.high, strict=True)
    )


def test_too_little_history_refuses_to_forecast():
    assert holt([0, 0, 0, 0, 0, 50, 60]) is None  # leading empty months are ignored
    assert holt([10, 20, 30]) is None


def test_forecast_never_goes_negative():
    result = holt([500, 400, 300, 200, 100, 50], horizon=3)
    assert result is not None and min(result.values + result.low) >= 0


def test_volatile_history_is_flagged():
    result = holt([10, 300, 5, 400, 20, 350])
    assert result is not None and result.notes


@pytest.mark.parametrize(
    "current,previous,expected", [(110, 100, 10.0), (90, 100, -10.0), (5, 0, None)]
)
def test_change(current, previous, expected):
    assert change(current, previous) == expected


def test_trend_direction_and_month_labels():
    assert trend_direction([1, 1, 1, 2, 2, 2]) == 100.0
    assert trend_direction([1, 2]) is None
    assert next_months("2026-11", 3) == ["2026-12", "2027-01", "2027-02"]
