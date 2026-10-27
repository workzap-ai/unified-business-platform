"""G11 (platform spec v1.4, 17.3): a trade guessed from weak words is a tool, not a fact."""

from types import SimpleNamespace

from app.modules.pi import service_conversation as sc


def conversation(brief: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(service_brief=brief or {})


def found(stated: bool) -> dict:
    return {
        "industry": ["Air conditioning"],
        "industry_keys": ["x"],
        "industry_stated": stated,
        "industry_knowledge": "AC units, gas refills, ...",
    }


def test_a_guess_carries_no_trade_knowledge() -> None:
    out = sc.unconfirmed_trade(found(False), conversation())
    assert out["industry_unconfirmed"] is True
    assert out["industry_knowledge"] == sc.UNCONFIRMED_TRADE
    assert "AC units" not in out["industry_knowledge"]


def test_a_stated_trade_is_kept_and_remembered() -> None:
    chat = conversation()
    out = sc.unconfirmed_trade(found(True), chat)
    assert out["industry_knowledge"].startswith("AC units")
    assert chat.service_brief["industry_confirmed"] is True


def test_once_confirmed_a_later_weak_turn_keeps_the_knowledge() -> None:
    out = sc.unconfirmed_trade(found(False), conversation({"industry_confirmed": True}))
    assert out["industry_knowledge"].startswith("AC units")
