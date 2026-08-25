from decimal import Decimal

import pytest

from invoice.totals import Line, apply_discount, line_total, subtotal, total_with_tax


def test_line_total():
    assert line_total(Line("A", 3, Decimal("2.50"))) == Decimal("7.50")


def test_subtotal():
    assert subtotal([Line("A", 1, Decimal("1.10")), Line("B", 2, Decimal("0.45"))]) == Decimal("2.00")


def test_discount_bounds():
    assert apply_discount(Decimal("10"), Decimal("25")) == Decimal("7.5")
    with pytest.raises(ValueError):
        apply_discount(Decimal("10"), Decimal("120"))


def test_total_with_tax_simple():
    assert total_with_tax([Line("A", 2, Decimal("5.00"))], Decimal("0.10")) == Decimal("11.00")


def test_total_rounds_once_not_per_line():
    # Three lines of 0.10 at 5% tax: 0.315 rounds to 0.32 once; rounding each line gives 0.33.
    basket = [Line("A", 1, Decimal("0.10")), Line("B", 1, Decimal("0.10")), Line("C", 1, Decimal("0.10"))]
    assert total_with_tax(basket, Decimal("0.05")) == Decimal("0.32")
