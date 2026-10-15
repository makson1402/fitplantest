from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def round_half_up(x: float, ndigits: int = 0) -> float:
    q = Decimal(1).scaleb(-ndigits)
    return float(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))
