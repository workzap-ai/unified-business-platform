"""The linking threshold follows what staff confirm and reject (spec 8.10)."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.modules.pi import brain_config, learning_links

NOW = datetime(2026, 10, 23, 3, 0, tzinfo=UTC)


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, row: object) -> None:
        self.added.append(row)

    async def scalars(self, query):
        return []


def test_the_threshold_starts_at_sixty_and_stays_inside_its_range():
    assert learning_links.threshold_for(None, "dental_clinics") == Decimal("0.6")
    rules = {"brain": {"link_thresholds": {"dental_clinics": 99, "bakeries": 10}}}
    assert learning_links.threshold_for(rules, "dental_clinics") == Decimal("0.85")
    assert learning_links.threshold_for(rules, "bakeries") == Decimal("0.5")
    assert learning_links.threshold_for(rules, "restaurants") == Decimal("0.6")
    assert learning_links.threshold_for(
        {"brain": {"link_thresholds": {"x": True}}}, "x"
    ) == Decimal("0.6")


def test_customers_with_no_industry_yet_share_the_other_threshold():
    rules = {"brain": {"link_thresholds": {"_other": 70}}}
    assert learning_links.threshold_for(rules, None) == Decimal("0.7")
    assert learning_links.threshold_for(rules, "dental_clinics") == Decimal("0.6")


def test_it_rises_when_staff_reject_many_and_falls_when_they_almost_never_do():
    assert learning_links.next_pct(60, confirmed=5, rejected=5) == 65
    assert learning_links.next_pct(60, confirmed=7, rejected=3) == 60  # 30%: leave it
    assert learning_links.next_pct(60, confirmed=19, rejected=1) == 55  # 5% over 20 decisions
    assert learning_links.next_pct(60, confirmed=9, rejected=0) == 60  # too few to make it easier
    assert learning_links.next_pct(85, confirmed=0, rejected=12) == 85  # top of the range
    assert learning_links.next_pct(50, confirmed=30, rejected=0) == 50  # bottom of the range
    assert learning_links.next_pct(60, confirmed=3, rejected=2) == 60  # fewer than ten


async def test_one_step_a_week_per_industry_and_every_move_is_logged(monkeypatch):
    async def fake(session, scope, since):
        return {
            "dental_clinics": {"confirmed": 4, "rejected": 8},
            "_other": {"confirmed": 8, "rejected": 2},
        }

    monkeypatch.setattr(learning_links, "decisions", fake)
    session = FakeSession()
    settings = SimpleNamespace(response_rules={})
    scope = SimpleNamespace(tenant_id=1, environment_id=1)
    out = await learning_links.tune(session, scope, settings, NOW)
    assert out == {"moved": {"dental_clinics": 65}}
    assert settings.response_rules["brain"]["link_thresholds"] == {"dental_clinics": 65}
    assert [r.kind for r in session.added] == ["link_threshold"]
    assert brain_config.link_pct(settings.response_rules, "dental_clinics") == 65
