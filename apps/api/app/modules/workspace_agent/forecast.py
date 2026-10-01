"""Small, explainable forecasts over exact monthly series. No external services.

Holt's linear trend (double exponential smoothing) with an 80% band from the one-step
residuals. It refuses to forecast from too little history instead of guessing, and
every result says which method and how many points it used, so the agent can state
its confidence honestly.
"""

import math
from dataclasses import dataclass, field

MIN_POINTS = 4  # fewer non-empty months than this: no forecast
Z80 = 1.2816  # two-sided 80% normal interval


@dataclass(frozen=True)
class Forecast:
    values: list[float]
    low: list[float]
    high: list[float]
    method: str = "Holt linear trend (80% range)"
    history_points: int = 0
    notes: list[str] = field(default_factory=list)


def holt(
    history: list[float], horizon: int = 3, alpha: float = 0.5, beta: float = 0.3
) -> Forecast | None:
    """Forecast ``horizon`` future periods, or None when history is too thin."""
    points = list(history)
    while points and points[0] == 0:  # months before the business started
        points.pop(0)
    if len([p for p in points if p]) < MIN_POINTS or horizon < 1:
        return None
    level, trend = points[0], points[1] - points[0]
    residuals: list[float] = []
    for value in points[1:]:
        predicted = level + trend
        residuals.append(value - predicted)
        previous = level
        level = alpha * value + (1 - alpha) * (level + trend)
        trend = beta * (level - previous) + (1 - beta) * trend
    sigma = math.sqrt(sum(r * r for r in residuals) / max(len(residuals) - 1, 1))
    values, low, high = [], [], []
    for step in range(1, horizon + 1):
        estimate = max(level + step * trend, 0.0)
        spread = Z80 * sigma * math.sqrt(step)
        values.append(round(estimate, 2))
        low.append(round(max(estimate - spread, 0.0), 2))
        high.append(round(estimate + spread, 2))
    notes = []
    if sigma > abs(level) * 0.5 and level:
        notes.append("History is volatile, so the range is wide.")
    return Forecast(values, low, high, history_points=len(points), notes=notes)


def change(current: float, previous: float) -> float | None:
    """Percent change, or None when there is no baseline."""
    if not previous:
        return None
    return round((current - previous) / abs(previous) * 100, 1)


def trend_direction(history: list[float], window: int = 3) -> float | None:
    """Last ``window`` periods vs the ``window`` before, as a percent change."""
    if len(history) < window * 2:
        return None
    return change(sum(history[-window:]), sum(history[-2 * window : -window]))


def next_months(last: str, count: int) -> list[str]:
    """YYYY-MM labels after ``last``."""
    year, month = (int(p) for p in last.split("-"))
    labels = []
    for _ in range(count):
        month += 1
        if month == 13:
            year, month = year + 1, 1
        labels.append(f"{year:04d}-{month:02d}")
    return labels
