from decimal import Decimal
from types import SimpleNamespace

from app.modules.pi import memory_ledger


def test_scope_words_use_the_quote_included_list_or_the_solution_components():
    quote = SimpleNamespace(content={"included": ["a sheet", " ", "alerts"]})
    assert memory_ledger.scope_words(quote) == "a sheet; alerts"
    solution = SimpleNamespace(content={"components": [{"text": "one"}, {"text": "two"}]})
    assert memory_ledger.scope_words(solution) == "one; two"
    assert memory_ledger.scope_words(SimpleNamespace(content={})) == ""


def test_price_words_keep_the_figure_as_entered_and_never_invent_one():
    doc = SimpleNamespace(
        total=Decimal("1250000.50"), currency="PKR", ref="Q-0002", version=1, approved_by=None
    )
    assert memory_ledger.price_words(doc) == "1250000.50 PKR (Q-0002, version 1, approved by staff)"
    assert memory_ledger.price_words(SimpleNamespace(total=None, ref="Q-1")) == ""
    assert memory_ledger.price_words(SimpleNamespace(total=Decimal("0"), ref="Q-1")) == ""
