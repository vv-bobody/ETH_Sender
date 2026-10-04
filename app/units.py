"""Amounts: the token's smallest units ↔ ordinary numbers, and how they are written in the log and the table."""
from __future__ import annotations

from decimal import ROUND_DOWN, Decimal, localcontext

PRECISION = 100  # balances in wei reach 30 digits, the standard 28 are not enough


def to_raw(value: Decimal, decimals: int) -> int:
    """10.5 USDC → 10500000 (rounded down)."""
    with localcontext() as ctx:
        ctx.prec = PRECISION
        return int((value * (Decimal(10) ** decimals)).to_integral_value(rounding=ROUND_DOWN))


def from_raw(raw: int, decimals: int) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = PRECISION
        return Decimal(raw) / (Decimal(10) ** decimals)


def plain(value: Decimal) -> str:
    """A number without an exponent and trailing zeros: 1.50 → 1.5, 100 → 100."""
    text = f"{value:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def human(raw: int, decimals: int, max_decimals: int = 6) -> str:
    """An amount for the log and statuses: at most 6 decimal places, rounded down."""
    with localcontext() as ctx:
        ctx.prec = PRECISION
        value = from_raw(raw, decimals)
        shown = value.quantize(Decimal(1).scaleb(-max_decimals), rounding=ROUND_DOWN)
        if shown == 0 and raw > 0:
            shown = value  # less than 0.000001 — show every digit
        return plain(shown)


def gwei(wei: int) -> str:
    """Gas price in gwei for the log."""
    with localcontext() as ctx:
        ctx.prec = PRECISION
        value = from_raw(wei, 9)
        if 0 < value < Decimal("0.001"):
            return "<0.001"
        return plain(value.quantize(Decimal("0.000001"), rounding=ROUND_DOWN))
