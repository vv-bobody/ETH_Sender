"""Apply: checking the RPC and the token, polling balances with retries and rate limits (spec 5.1–5.2, 12.5)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from eth_account import Account

from app.apply import LIMIT_BACKOFF, RAISE_AFTER, ApplyError, Throttle, check_rpc, poll_balances, resolve_token
from app.networks import NETWORKS
from app.wallets import WalletEntry
from tests.fake_chain import FakeChain, FakeClock


def wallets(count: int) -> list[tuple[int, WalletEntry]]:
    entries = [WalletEntry(i + 1, i + 1, "", Account.from_key("0x" + f"{i + 1:04x}" * 16).address, None)
               for i in range(count)]
    return list(enumerate(entries))


def test_wrong_chain_id_is_reported_with_both_ids():
    chain = FakeChain(FakeClock(), chain_id=1)
    with pytest.raises(ApplyError, match="returned chain ID 1, expected 8453"):
        check_rpc(chain, NETWORKS["base"])


def test_unreachable_rpc_is_reported():
    chain = FakeChain(FakeClock())
    chain.failures["chain_id"] = 1
    with pytest.raises(ApplyError, match="does not respond"):
        check_rpc(chain, NETWORKS["arbitrum"])


def test_token_resolution():
    chain = FakeChain(FakeClock())
    base = NETWORKS["base"]
    assert resolve_token(chain, base, "native").label == "ETH"
    preset = resolve_token(chain, base, "usdc")
    assert preset.address == base.preset("usdc").address and preset.label == "USDC"
    chain.symbol, chain.decimals = "CAKE", 18
    custom = resolve_token(chain, NETWORKS["bsc"], "0x0e09fabb73bd3ade0a17ecc321fd13a19e81ce82")
    assert custom.label == "CAKE" and custom.decimals == 18
    assert custom.address == "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82"
    chain.code = False
    with pytest.raises(ApplyError, match="There is no contract"):
        resolve_token(chain, base, "usdt")


def test_balances_are_polled_with_retries():
    chain = FakeChain(FakeClock(), native=2 * 10**18, token=1_500_000)
    chain.failures["token_balance"] = 2  # two errors in a row — the third attempt succeeds
    rows: dict[int, dict] = {}
    progress: list[tuple[int, int]] = []
    token = resolve_token(chain, NETWORKS["base"], "usdc")
    failed = poll_balances(chain, token, wallets(3), rows.__setitem__,
                           lambda done, total: progress.append((done, total)), sleep=lambda s: None)
    assert failed == 0 and progress[-1] == (3, 3)
    assert all(changes == {"native_balance": Decimal(2), "token_balance": Decimal("1.5")} for changes in rows.values())

    chain.failures["native_balance"] = 99
    rows.clear()
    failed = poll_balances(chain, token, wallets(3), rows.__setitem__, lambda *_: None, sleep=lambda s: None)
    assert failed == 3 and all("balance_error" in changes for changes in rows.values())


def test_rate_limited_rpc_is_polled_without_errors():
    """An RPC lets through at most 10 requests a second: polling slows down by itself (spec 12.5, criterion 6)."""
    clock = FakeClock()
    chain = FakeChain(clock, native=10**18, token=5_000_000)
    chain.rate_limit = (10, 1.0)
    waits: list[int] = []
    rows: dict[int, dict] = {}
    token = resolve_token(chain, NETWORKS["base"], "usdc")
    failed = poll_balances(chain, token, wallets(50), rows.__setitem__, lambda *_: None, on_limit=waits.append,
                           sleep=clock.sleep, clock=clock)
    assert failed == 0 and len(rows) == 50 and all("token_balance" in changes for changes in rows.values())
    assert chain.limited > 0 and waits and set(waits) <= set(LIMIT_BACKOFF)


def test_rate_limit_gives_up_after_five_attempts():
    clock = FakeClock()
    chain = FakeChain(clock)
    chain.rate_limit = (0, 1.0)  # the RPC never answers
    rows: dict[int, dict] = {}
    waits: list[int] = []
    token = resolve_token(chain, NETWORKS["base"], "native")
    failed = poll_balances(chain, token, wallets(1), rows.__setitem__, lambda *_: None, on_limit=waits.append,
                           sleep=clock.sleep, clock=clock)
    assert failed == 1 and "balance_error" in rows[0]
    assert waits == list(LIMIT_BACKOFF) and chain.limited == 5  # 1, 2, 4, 8 s between 5 attempts


def test_throttle_halves_requests_after_a_limit_and_grows_back():
    clock = FakeClock()
    throttle = Throttle(5, clock=clock, sleep=clock.sleep)
    assert throttle.limited(0) == 1 and throttle.limit == 2 and throttle.resume_at == 1
    assert throttle.limited(1) == 2 and throttle.limit == 1 and throttle.resume_at == 2
    throttle.acquire()  # everyone waits for the pause after a limit
    assert clock.now == 2
    throttle.release(ok=True)
    for _ in range(RAISE_AFTER - 1):
        throttle.acquire()
        throttle.release(ok=True)
    assert throttle.limit == 2  # 20 successful requests in a row — one more at once
