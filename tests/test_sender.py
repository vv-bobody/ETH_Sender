"""Sending from a wallet and the mailing: every retry scenario of the spec (5.5–5.8)."""
from __future__ import annotations

import math
import random
import threading
from decimal import Decimal

from eth_account import Account

from app.chain import ChainError
from app.networks import NETWORKS
from app.sender import BUMP, PENDING_CHECKS, PENDING_PAUSE, Job, Mailing, Outcome, Plan, Token, WalletSender
from app.wallets import WalletEntry
from tests.fake_chain import FakeChain, FakeClock

KEY = "0x" + "11" * 32
RECIPIENT = "0x2222222222222222222222222222222222222222"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
ETH = Token(None, 18, "ETH")
USDC_TOKEN = Token(USDC, 6, "USDC")


def wallet(key: str = KEY, num: int = 1, name: str = "Test") -> WalletEntry:
    return WalletEntry(num, num, name, Account.from_key(key).address, RECIPIENT, private_key=key)


def plan(mode: str = "all", *, percent: str = "100", rmin: str | None = None, rmax: str | None = None,
         k: str = "1.2", timeout: int = 120, delay: tuple[int, int] = (0, 0), order: str = "sequential") -> Plan:
    return Plan(mode, Decimal(percent), Decimal(rmin) if rmin else None, Decimal(rmax) if rmax else None,
                Decimal(k), timeout, delay[0], delay[1], order)


class Recorder:
    """Keeps messages as the window would show them in English, the default language."""

    def __init__(self) -> None:
        self.logs: list[tuple[str, str]] = []
        self.statuses: list[tuple[str, list[str], str | None]] = []

    def progress(self, status, marks: list[str], tx_hash: str | None) -> None:
        self.statuses.append((str(status), marks, tx_hash))

    def log(self, text, level: str = "info") -> None:
        self.logs.append((level, str(text)))


class MaxRng(random.Random):
    """Always picks the upper bound — to check an amount larger than the balance."""

    def randint(self, a: int, b: int) -> int:
        return b


def run(chain: FakeChain, clock: FakeClock, *, network: str = "arbitrum", token: Token = ETH, rng=None,
        **plan_kwargs):
    sender = WalletSender(chain, NETWORKS[network], token, plan(**plan_kwargs), wallet(), Recorder(),
                          sleep=clock.sleep, clock=clock, rng=rng or random.Random(7))
    return sender.run(), sender.reporter


def ceil_bump(value: int) -> int:
    return math.ceil(Decimal(value) * BUMP)


# --- successful sending ----------------------------------------------------------------------------


def test_native_all_on_base_reserves_gas_and_l1_fee():
    clock = FakeClock()
    chain = FakeChain(clock, native=10**18, base_fee=100, tip=10, gas=21000, l1_fee=1000)
    result, _ = run(chain, clock, network="base")
    assert result.outcome is Outcome.OK
    assert result.marks == ["ok"]
    [tx] = chain.sent
    max_fee = math.ceil(110 * Decimal("1.2"))
    assert tx["max_fee"] == max_fee and tx["priority_fee"] == 12
    assert tx["value"] == 10**18 - (21000 * max_fee + 1200)  # gas + L1 fee × multiplier
    assert tx["type"] == 2 and tx["nonce"] == 0
    assert result.tx_hash == tx["hash"]


def test_bsc_uses_legacy_gas_price():
    clock = FakeClock()
    chain = FakeChain(clock, legacy=True, base_fee=100, tip=0)
    result, _ = run(chain, clock, network="bsc")
    assert result.outcome is Outcome.OK
    [tx] = chain.sent
    assert tx["type"] == 0 and tx["max_fee"] == 120


def test_erc20_range_amount_is_within_range_and_rounded_to_4_places():
    clock = FakeClock()
    chain = FakeChain(clock, token=100_000_000, token_address=USDC)
    result, _ = run(chain, clock, token=USDC_TOKEN, mode="range", rmin="10", rmax="15")
    assert result.outcome is Outcome.OK and str(result.status).startswith("Success: ")
    [tx] = chain.sent
    amount = int.from_bytes(tx["data"][36:68], "big")
    assert 10_000_000 <= amount <= 15_000_000 and amount % 100 == 0
    assert tx["to"].lower() == USDC.lower() and tx["value"] == 0


def test_erc20_percent_of_balance():
    clock = FakeClock()
    chain = FakeChain(clock, token=33_000_001, token_address=USDC)
    result, _ = run(chain, clock, token=USDC_TOKEN, mode="percent", percent="50")
    assert result.outcome is Outcome.OK
    assert int.from_bytes(chain.sent[0]["data"][36:68], "big") == 16_500_000  # rounded down


def test_range_bigger_than_balance_sends_whole_balance_if_it_is_in_range():
    clock = FakeClock()
    chain = FakeChain(clock, token=12_000_000, token_address=USDC)
    result, _ = run(chain, clock, token=USDC_TOKEN, mode="range", rmin="10", rmax="15", rng=MaxRng())
    assert result.outcome is Outcome.OK
    assert int.from_bytes(chain.sent[0]["data"][36:68], "big") == 12_000_000


# --- checking the result ---------------------------------------------------------------------------


def test_missing_transfer_event_needs_check_and_is_not_retried():
    clock = FakeClock()
    chain = FakeChain(clock, token=50_000_000, token_address=USDC)
    chain.transfer_event = False
    result, _ = run(chain, clock, token=USDC_TOKEN)
    assert result.outcome is Outcome.CHECK and str(result.status) == "Needs review"
    assert len(chain.sent) == 1 and result.marks == ["warn"]


def test_transfer_amount_mismatch_needs_check():
    clock = FakeClock()
    chain = FakeChain(clock, token=50_000_000, token_address=USDC)
    chain.transfer_delta = -1
    result, _ = run(chain, clock, token=USDC_TOKEN)
    assert result.outcome is Outcome.CHECK and len(chain.sent) == 1


# --- retries: replacement by nonce, broken connections, status 0 ----------------------------------


def test_stuck_transaction_is_replaced_with_same_nonce_and_higher_fee():
    clock = FakeClock()
    chain = FakeChain(clock)
    chain.script = ["hang", "mine"]
    result, recorder = run(chain, clock, timeout=120)
    assert result.outcome is Outcome.OK and result.marks == ["retry", "ok"]
    first, second = chain.sent
    assert first["nonce"] == second["nonce"]
    assert second["max_fee"] >= ceil_bump(first["max_fee"])
    assert second["priority_fee"] >= ceil_bump(first["priority_fee"])
    assert clock.now >= 120 + 10  # waited for the timeout and 10 s before the retry
    assert any("replacement with the same nonce" in text for _, text in recorder.logs)


def test_lost_connection_resends_the_same_signed_transaction():
    clock = FakeClock()
    chain = FakeChain(clock)
    chain.script = ["rpc", "mine"]
    result, _ = run(chain, clock)
    assert result.outcome is Outcome.OK and result.marks == ["retry", "ok"]
    assert chain.sent[0]["hash"] == chain.sent[1]["hash"]


def test_accepted_despite_lost_response_is_found_before_resending():
    clock = FakeClock()
    chain = FakeChain(clock)
    chain.script = ["rpc_accepted"]
    result, _ = run(chain, clock)
    assert result.outcome is Outcome.OK and result.marks == ["ok"]
    assert len(chain.sent) == 1  # a second send was not needed


def test_rejected_by_node_is_prepared_again_with_the_same_nonce():
    clock = FakeClock()
    chain = FakeChain(clock)
    chain.script = ["rejected", "mine"]
    result, recorder = run(chain, clock)
    assert result.outcome is Outcome.OK and result.marks == ["retry", "ok"]
    assert chain.sent[0]["nonce"] == chain.sent[1]["nonce"]
    assert chain.estimates == [10**18, 10**18]  # gas was estimated again
    assert any("the node rejected: intrinsic gas too low" in text for _, text in recorder.logs)


def test_lost_response_then_nonce_too_low_waits_instead_of_sending_again():
    """The connection broke, but the transaction went out; by the retry it is in a block, and the node answers
    "nonce too low". A new transaction with a new nonce would be a second transfer — wait for the first receipt."""
    clock = FakeClock()
    chain = FakeChain(clock, mine_after=11)  # gets into a block in 11 s — after the check before the retry
    chain.script = ["rpc_accepted", "nonce_used"]
    result, _ = run(chain, clock)
    assert result.outcome is Outcome.OK
    assert {tx["hash"] for tx in chain.sent} == {chain.sent[0]["hash"]}  # one and the same transaction only
    assert all(tx["nonce"] == 0 for tx in chain.sent)


def test_already_known_counts_as_sent():
    clock = FakeClock()
    chain = FakeChain(clock)
    chain.script = ["known"]
    result, _ = run(chain, clock)
    assert result.outcome is Outcome.OK and len(chain.sent) == 1


def test_failed_transaction_is_retried_with_next_nonce():
    clock = FakeClock()
    chain = FakeChain(clock)
    chain.script = ["fail", "mine"]
    result, _ = run(chain, clock)
    assert result.outcome is Outcome.OK and result.marks == ["retry", "ok"]
    assert chain.sent[1]["nonce"] == chain.sent[0]["nonce"] + 1


def test_underpriced_replacement_is_raised_again():
    clock = FakeClock()
    chain = FakeChain(clock)
    chain.script = ["hang", "underpriced", "mine"]
    result, _ = run(chain, clock)
    assert result.outcome is Outcome.OK and result.marks == ["retry", "retry", "ok"]
    first, second, third = chain.sent
    assert first["nonce"] == second["nonce"] == third["nonce"]
    assert third["max_fee"] >= ceil_bump(second["max_fee"])


def test_foreign_transaction_took_nonce_then_fresh_nonce_is_used():
    clock = FakeClock()
    chain = FakeChain(clock)
    chain.script = ["nonce_low", "mine"]
    result, _ = run(chain, clock)
    assert result.outcome is Outcome.OK
    assert chain.sent[1]["nonce"] == chain.sent[0]["nonce"] + 1


def test_never_mined_after_four_attempts_is_unconfirmed():
    clock = FakeClock()
    chain = FakeChain(clock)
    chain.script = ["hang"] * 4
    result, _ = run(chain, clock, timeout=60)
    assert result.outcome is Outcome.UNCONFIRMED and str(result.status) == "Not confirmed"
    assert result.marks == ["retry", "retry", "retry", "warn"]
    assert len({tx["nonce"] for tx in chain.sent}) == 1  # only replacements — a double transfer is impossible
    fees = [tx["max_fee"] for tx in chain.sent]
    assert all(later >= ceil_bump(earlier) for earlier, later in zip(fees, fees[1:]))
    assert result.sent and result.tx_hash == chain.sent[-1]["hash"]


def test_rpc_down_while_preparing_fails_after_four_attempts_without_sending():
    clock = FakeClock()
    chain = FakeChain(clock)
    chain.failures["nonces"] = 10
    result, _ = run(chain, clock)
    assert result.outcome is Outcome.ERROR and str(result.status) == "Error: RPC not responding"
    assert result.marks == ["retry", "retry", "retry", "fail"]
    assert chain.sent == [] and not result.sent
    assert clock.now == 30  # three pauses of 10 s


def test_replacement_for_native_all_lowers_the_amount_by_the_fee_increase():
    clock = FakeClock()
    chain = FakeChain(clock, native=10**18)
    chain.script = ["hang", "mine"]
    result, _ = run(chain, clock)
    assert result.outcome is Outcome.OK
    first, second = chain.sent
    assert second["value"] == 10**18 - 21000 * second["max_fee"]
    assert second["value"] < first["value"]


# --- errors without retries ----------------------------------------------------------------------


def test_pending_foreign_transaction_skips_wallet():
    clock = FakeClock()
    chain = FakeChain(clock, nonce=5, pending_nonce=6)
    result, _ = run(chain, clock)
    assert result.outcome is Outcome.SKIPPED and "pending" in str(result.status)
    assert chain.sent == [] and result.marks == [] and not result.sent
    assert clock.now == PENDING_CHECKS * PENDING_PAUSE  # checked again before skipping (spec 13.4)


def test_nonce_counted_only_as_pending_for_a_moment_does_not_skip_wallet():
    """Right after a transaction gets into a block a node may count its nonce only as pending (spec 13.4)."""
    clock = FakeClock()
    chain = FakeChain(clock, nonce=5, pending_nonce=6)
    nonces = chain.nonces

    def lagging(address):
        latest, pending = nonces(address)
        chain.pending_nonce, chain.nonce = None, 6  # by the next request the node has caught up
        return latest, pending

    chain.nonces = lagging
    result, _ = run(chain, clock, network="avalanche")
    assert result.outcome is Outcome.OK and chain.sent[0]["nonce"] == 6


def test_native_all_on_avalanche_reserves_gas_at_the_minimum_price():
    """AVAX: about 5 gwei of base fee and an almost zero tip; the reserve covers the whole gas limit (spec 13.4)."""
    clock = FakeClock()
    chain = FakeChain(clock, native=10**17, base_fee=5_030_191_349, tip=1, gas=21000, chain_id=43114)
    result, _ = run(chain, clock, network="avalanche")
    assert result.outcome is Outcome.OK
    [tx] = chain.sent
    max_fee = math.ceil((5_030_191_349 + 1) * Decimal("1.2"))
    assert tx["type"] == 2 and tx["max_fee"] == max_fee and tx["value"] == 10**17 - 21000 * max_fee


def test_zero_balance_skips_wallet():
    clock = FakeClock()
    chain = FakeChain(clock, native=0)
    result, _ = run(chain, clock)
    assert result.outcome is Outcome.SKIPPED and str(result.status) == "Skipped: zero balance"
    assert result.status.render("ru") == "Пропущен: баланс 0"  # the Russian text is as before (spec 12.2)


def test_not_enough_native_for_token_gas_skips_wallet():
    clock = FakeClock()
    chain = FakeChain(clock, native=1000, token=5_000_000, token_address=USDC)
    result, _ = run(chain, clock, token=USDC_TOKEN)
    assert result.outcome is Outcome.SKIPPED and str(result.status) == "Skipped: low ETH for gas"
    assert "need ~" in str(result.detail) and result.status.render("ru") == "Пропущен: мало ETH на газ"


def test_balance_below_range_minimum_skips_wallet():
    clock = FakeClock()
    chain = FakeChain(clock, token=5_200_000, token_address=USDC)
    result, _ = run(chain, clock, token=USDC_TOKEN, mode="range", rmin="10", rmax="15")
    assert result.outcome is Outcome.SKIPPED
    assert str(result.detail) == "Balance 5.2 USDC is below the range minimum 10 USDC"
    assert result.detail.render("ru") == "Баланс 5.2 USDC меньше минимума диапазона 10 USDC"


def test_contract_rejecting_transfer_is_an_error_without_retries():
    clock = FakeClock()
    chain = FakeChain(clock, token=5_000_000, token_address=USDC)
    chain.estimate_error = ChainError(ChainError.REVERTED, "execution reverted: blacklisted")
    result, _ = run(chain, clock, token=USDC_TOKEN)
    assert result.outcome is Outcome.ERROR and str(result.status) == "Error: transfer reverted"
    assert result.marks == ["fail"] and chain.sent == [] and clock.now == 0


def test_insufficient_funds_on_send_is_an_error_without_retries():
    clock = FakeClock()
    chain = FakeChain(clock)
    chain.script = ["insufficient"]
    result, _ = run(chain, clock)
    assert result.outcome is Outcome.ERROR and str(result.status) == "Error: insufficient funds"
    assert len(chain.sent) == 1 and result.marks == ["fail"]


# --- the mailing -----------------------------------------------------------------------------------


class Events:
    def __init__(self) -> None:
        self.updates: list[tuple[int, dict]] = []
        self.logs: list[tuple[str, str]] = []

    def update(self, row: int, changes: dict) -> None:
        self.updates.append((row, changes))

    def log(self, text, level: str = "info") -> None:
        self.logs.append((level, str(text)))

    def progress(self, done: int, total: int, text) -> None:
        pass

    def final(self, row: int) -> dict:
        return [changes for r, changes in self.updates if r == row and changes.get("state") != "sending"
                and "state" in changes][-1]


def keys(n: int) -> list[str]:
    return ["0x" + f"{i + 1:02x}" * 32 for i in range(n)]


def mailing(chain, clock, jobs, events, *, stop=None, wait=None, **plan_kwargs) -> Mailing:
    stop = stop or threading.Event()
    return Mailing(chain, NETWORKS["arbitrum"], ETH, plan(**plan_kwargs), jobs, events, stop,
                   sleep=clock.sleep, clock=clock, wait=wait or (lambda s: (clock.sleep(s), stop.is_set())[1]),
                   rng=random.Random(3))


def test_pause_only_after_wallets_that_sent_a_transaction():
    clock = FakeClock()
    chain = FakeChain(clock)
    wallets = [wallet(key, num=i + 1, name=f"W{i + 1}") for i, key in enumerate(keys(3))]
    chain.native_by[wallets[1].sender] = 0  # the second wallet is skipped
    events = Events()
    jobs = [Job(i, w) for i, w in enumerate(wallets)]
    counts = mailing(chain, clock, jobs, events, delay=(5, 5)).run()
    assert counts[Outcome.OK] == 2 and counts[Outcome.SKIPPED] == 1
    assert [text for _, text in events.logs if text.startswith("Delay")] == ["Delay 5 s"]
    assert str(events.final(1)["status"]) == "Skipped: zero balance"
    assert events.logs[-1][1] == "Done: 2 succeeded, 0 need review, 0 not confirmed, 0 failed, 1 skipped"


def test_random_order_shuffles_wallets():
    clock = FakeClock()
    chain = FakeChain(clock)
    wallets = [wallet(key, num=i + 1) for i, key in enumerate(keys(6))]
    events = Events()
    mailing(chain, clock, [Job(i, w) for i, w in enumerate(wallets)], events, order="random").run()
    started = []
    for row, changes in events.updates:
        if changes.get("state") == "sending" and row not in started:
            started.append(row)
    assert sorted(started) == list(range(6)) and started != list(range(6))


def test_stop_during_pause_stops_immediately_and_marks_the_rest():
    clock = FakeClock()
    chain = FakeChain(clock)
    wallets = [wallet(key, num=i + 1) for i, key in enumerate(keys(3))]
    stop = threading.Event()
    events = Events()

    def wait(seconds: float) -> bool:
        stop.set()  # Stop was pressed during the very first delay
        return True

    counts = mailing(chain, clock, [Job(i, w) for i, w in enumerate(wallets)], events, stop=stop, wait=wait,
                     delay=(30, 30)).run()
    assert counts[Outcome.OK] == 1 and counts[Outcome.STOPPED] == 2
    assert {str(events.final(row)["status"]) for row in (1, 2)} == {"Not processed (stopped)"}
    assert len(chain.sent) == 1


def test_stop_pressed_during_a_wallet_finishes_it_first():
    clock = FakeClock()
    chain = FakeChain(clock)
    wallets = [wallet(key, num=i + 1) for i, key in enumerate(keys(2))]
    stop = threading.Event()
    events = Events()
    chain.script = ["hang", "mine"]  # the first wallet needs a retry
    original = chain.send_raw

    def send_and_press_stop(raw: bytes) -> str:
        stop.set()
        return original(raw)

    chain.send_raw = send_and_press_stop
    counts = mailing(chain, clock, [Job(i, w) for i, w in enumerate(wallets)], events, stop=stop).run()
    assert counts[Outcome.OK] == 1 and counts[Outcome.STOPPED] == 1
    assert events.final(0)["marks"] == ["retry", "ok"]  # the current wallet was finished, with its retry
