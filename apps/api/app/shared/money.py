"""Money is Decimal in Python and NUMERIC in PostgreSQL. Never float."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from pydantic import Field, StringConstraints
from sqlalchemy import Numeric

CENT = Decimal("0.01")
MONEY_SQL = Numeric(14, 2)
QUANTITY_SQL = Numeric(14, 3)
RATE_SQL = Numeric(7, 4)

Money = Annotated[Decimal, Field(max_digits=14, decimal_places=2, ge=0)]
SignedMoney = Annotated[Decimal, Field(max_digits=14, decimal_places=2)]
Rate = Annotated[Decimal, Field(max_digits=7, decimal_places=4, ge=0, le=1)]
Currency = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Z]{3}$")
]


def quantize(value: Decimal) -> Decimal:
    if isinstance(value, float):  # defensive: floats must never reach money paths
        raise TypeError("Money must be Decimal")
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def line_total(quantity: Decimal | int, unit_price: Decimal, discount: Decimal) -> Decimal:
    gross = quantize(Decimal(quantity) * unit_price)
    return max(quantize(gross - discount), Decimal("0.00"))


def tax_for(amount: Decimal, rate: Decimal) -> Decimal:
    return quantize(amount * rate)


def format_money(amount: Decimal, currency: str) -> str:
    return f"{currency} {quantize(amount):,.2f}"


@dataclass(frozen=True, slots=True)
class Totals:
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    total: Decimal


def compute_totals(
    lines: list[tuple[Decimal, Decimal, Decimal]], tax_rate: Decimal
) -> tuple[list[Decimal], Totals]:
    """lines are (quantity, unit_price, discount). Returns per-line totals and document totals.

    Deterministic: every intermediate amount is quantized to cents with ROUND_HALF_UP.
    """
    line_totals: list[Decimal] = []
    subtotal = discount_total = Decimal("0.00")
    for quantity, unit_price, discount in lines:
        gross = quantize(Decimal(quantity) * unit_price)
        if discount > gross:
            raise ValueError("Discount exceeds line amount")
        subtotal += gross
        discount_total += quantize(discount)
        line_totals.append(quantize(gross - discount))
    taxable = subtotal - discount_total
    tax = tax_for(taxable, tax_rate)
    return line_totals, Totals(
        quantize(subtotal), quantize(discount_total), tax, quantize(taxable + tax)
    )
