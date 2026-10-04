"""Total balances: exact sums, one sender counted once, wallets whose balance check failed (spec 12.1)."""
from __future__ import annotations

from decimal import Decimal

from app.totals import State, WalletBalance, total
from app.units import from_raw


def wallet(num: int, sender: str, token: str | None = "1", native: str | None = "0.1", **flags) -> WalletBalance:
    return WalletBalance(num, sender, Decimal(token) if token is not None else None,
                         Decimal(native) if native is not None else None, **flags)


def test_sums_of_18_decimal_tokens_are_exact():
    """USDT and USDC in BSC have 18 decimal places: the standard precision of Decimal would round the sum."""
    raw = 123_456_789_012_345_678_901_234_567  # 27 digits — more than float can hold
    balances = [WalletBalance(i, f"0x{i:040x}", from_raw(raw, 18), from_raw(raw + i, 18)) for i in range(50)]
    result = total(balances)
    assert result.state is State.READY and result.wallets == 50
    assert result.token == from_raw(raw * 50, 18)
    assert result.native == from_raw(raw * 50 + sum(range(50)), 18)


def test_a_sender_listed_twice_is_counted_once():
    result = total([wallet(1, "0xA", "10"), wallet(2, "0xA", "10"), wallet(3, "0xB", "5")])
    assert result.token == Decimal(15) and result.wallets == 2


def test_failed_wallets_are_left_out_and_named():
    result = total([wallet(1, "0xA", "10"), wallet(2, "0xB", None, None, failed=True),
                    wallet(3, "0xC", None, None, failed=True), wallet(4, "0xC", "7")])
    # 0xC failed in one row but loaded in another — it is known; 0xB is left out
    assert result.token == Decimal(17) and result.wallets == 2 and result.failed == (2,)


def test_checked_wallets_only():
    balances = [wallet(1, "0xA", "10", checked=True), wallet(2, "0xB", "5"), wallet(3, "0xA", "10")]
    result = total(balances, checked_only=True)
    assert result.token == Decimal(10) and result.wallets == 1
    assert total([wallet(1, "0xA")], checked_only=True).state is State.EMPTY  # nothing checked — no sums


def test_states_before_and_during_polling():
    assert total([wallet(1, "0xA", None, None)]).state is State.EMPTY  # Apply was not pressed yet
    assert total([wallet(1, "0xA"), wallet(2, "0xB", None, None, loading=True)]).state is State.LOADING
    assert total([]).state is State.EMPTY
