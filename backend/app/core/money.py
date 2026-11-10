from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def q2(value: Decimal) -> Decimal:
    """Round half-up to cents (rule 11)."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)
