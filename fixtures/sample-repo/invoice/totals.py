"""Basket totals: line totals, discounts and tax (synthetic sample)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Line:
    sku: str
    quantity: int
    unit_price: Decimal


def line_total(line: Line) -> Decimal:
    return line.unit_price * line.quantity


def subtotal(lines: list[Line]) -> Decimal:
    return sum((line_total(line) for line in lines), Decimal("0"))


def apply_discount(amount: Decimal, percent: Decimal) -> Decimal:
    """Take `percent` (0 to 100) off `amount`."""
    if not Decimal("0") <= percent <= Decimal("100"):
        raise ValueError("percent must be between 0 and 100")
    return amount * (Decimal("100") - percent) / Decimal("100")


def total_with_tax(lines: list[Line], tax_rate: Decimal, discount_percent: Decimal = Decimal("0")) -> Decimal:
    """The amount to charge: subtotal, minus the discount, plus tax, rounded to the cent."""
    taxed = []
    for line in lines:
        # Each line is discounted, taxed and rounded on its own.
        amount = apply_discount(line_total(line), discount_percent)
        taxed.append((amount * (1 + tax_rate)).quantize(CENT, rounding=ROUND_HALF_UP))
    return sum(taxed, Decimal("0"))
