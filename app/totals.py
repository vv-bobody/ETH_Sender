"""Total balances of the wallets: for the Total row, the checked wallets and the confirmation window (spec 12.1).

Sums are exact: balances are added with the same raised precision as in app/units.py, without rounding on the way.
A sender listed in wallets.txt several times is one wallet, so its balance is counted once.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import Enum

from app.units import PRECISION


@dataclass(frozen=True)
class WalletBalance:
    """What the table knows about one row: balances (None — not loaded) and whether polling failed or is running."""

    num: int
    sender: str
    token: Decimal | None
    native: Decimal | None
    failed: bool = False
    loading: bool = False
    checked: bool = False


class State(Enum):
    EMPTY = "empty"  # no balances yet: Apply was not pressed or failed — show "—"
    LOADING = "loading"  # balances are being polled — show "…"
    READY = "ready"


@dataclass(frozen=True)
class Total:
    state: State
    token: Decimal = Decimal(0)
    native: Decimal = Decimal(0)
    wallets: int = 0  # how many wallets the sums include
    failed: tuple[int, ...] = ()  # numbers of the wallets left out: their balance check failed


def total(balances: Iterable[WalletBalance], *, checked_only: bool = False) -> Total:
    """Sums over all wallets or only over the checked ones."""
    rows = list(balances)
    if checked_only:
        senders = {row.sender for row in rows if row.checked}
        rows = [row for row in rows if row.sender in senders]
    if any(row.loading for row in rows):
        return Total(State.LOADING)
    known: dict[str, WalletBalance] = {}
    failed: dict[str, int] = {}
    for row in rows:
        if row.token is not None and row.native is not None:
            known.setdefault(row.sender, row)
        elif row.failed:
            failed.setdefault(row.sender, row.num)
    failed_numbers = tuple(sorted(num for sender, num in failed.items() if sender not in known))
    if not known and not failed_numbers:
        return Total(State.EMPTY)
    with localcontext() as ctx:
        ctx.prec = PRECISION
        token = sum((row.token for row in known.values()), Decimal(0))
        native = sum((row.native for row in known.values()), Decimal(0))
    return Total(State.READY, token, native, len(known), failed_numbers)
