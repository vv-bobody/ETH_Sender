"""Sending from one wallet and the whole mailing (spec 5.3–5.8).

The main rule is never to send twice. A new nonce is taken only if the transaction with the previous nonce got into
a block with the "failed" status, or the nonce was taken by someone else's transaction. In every other case
the retry goes with the same nonce, so only one of the transactions can go through.
"""
from __future__ import annotations

import math
import random
import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, localcontext
from enum import Enum
from typing import Protocol

from eth_account import Account

from app.chain import ChainError, Fees, find_transfer, transfer_data
from app.i18n import Text, t
from app.networks import Network
from app.text import short_address
from app.units import from_raw, gwei, human, plain, to_raw
from app.wallets import WalletEntry

MAX_ATTEMPTS = 4  # 1 attempt and up to 3 retries
RETRY_PAUSE = 10  # sec before a retry
POLL_INTERVAL = 2  # sec between receipt requests
BUMP = Decimal("1.15")  # the gas price of a replacement is at least +15% over the previous one
# A pending transaction is checked again before the wallet is skipped: right after a transaction gets into a block,
# an RPC node may still count its nonce only as pending (spec 13.4)
PENDING_CHECKS = 2
PENDING_PAUSE = 3  # sec
RANGE_DECIMALS = 4  # a random amount from the range is rounded down to 4 decimal places

# How an attempt ended — a dot in the Attempts column
ACTIVE, RETRY, OK_MARK, WARN, FAIL = "active", "retry", "ok", "warn", "fail"


class Outcome(Enum):
    OK = "ok"
    CHECK = "check"  # went through, but the Transfer event is missing or does not match
    UNCONFIRMED = "unconfirmed"
    ERROR = "error"
    SKIPPED = "skipped"
    STOPPED = "stopped"


@dataclass(frozen=True)
class Token:
    address: str | None  # None — the native coin of the network
    decimals: int
    label: str

    @property
    def native(self) -> bool:
        return self.address is None


@dataclass(frozen=True)
class Plan:
    amount_mode: str  # all | percent | range
    percent: Decimal
    range_min: Decimal | None
    range_max: Decimal | None
    gas_multiplier: Decimal
    tx_timeout: int
    delay_min: int = 0
    delay_max: int = 0
    order: str = "sequential"


@dataclass
class Result:
    outcome: Outcome
    status: Text  # short — for the table
    detail: Text  # in full — for the tooltip
    sent: bool  # whether a transaction was sent: the delay is made only after such wallets
    tx_hash: str | None = None
    marks: list[str] = field(default_factory=list)


class Reporter(Protocol):
    def progress(self, status: Text, marks: list[str], tx_hash: str | None) -> None: ...

    def log(self, text: Text, level: str = "info") -> None: ...


class _Skip(Exception):
    """Nothing to send or nothing to pay gas with — no retries (spec 5.7)."""

    def __init__(self, status: Text, detail: Text) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class _Fatal(_Skip):
    """An error that a retry will not fix."""


@dataclass
class _Sent:
    tx_hash: str
    raw: bytes
    nonce: int
    fees: Fees
    gas: int
    value: int
    amount: int
    broadcast: bool = False  # the node confirmed it accepted the transaction
    uncertain: bool = False  # the connection broke while sending: the transaction may have reached the network


@dataclass
class _Draft:
    nonce: int
    to: str
    value: int
    data: bytes
    gas: int
    fees: Fees
    amount: int


class WalletSender:
    """One wallet: preparing, sending, checking the result and retrying (spec 5.5–5.6)."""

    def __init__(self, chain, network: Network, token: Token, plan: Plan, wallet: WalletEntry, reporter: Reporter, *,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                 rng: random.Random | None = None) -> None:
        self.chain = chain
        self.network = network
        self.token = token
        self.plan = plan
        self.wallet = wallet
        self.reporter = reporter
        self.sleep = sleep
        self.clock = clock
        self.rng = rng or random.Random()
        self.inflight: list[_Sent] = []  # sent with the current nonce and without a receipt yet
        self.marks: list[str] = []
        self.sent_any = False
        self.last_hash: str | None = None
        self.last_fees: Fees | None = None
        self.min_fees: Fees | None = None  # after a "gas price too low" refusal the next attempt is not cheaper
        self.range_amount: int | None = None  # the amount from the range is picked once per wallet
        self.reason: Text = t("RPC not responding")  # in short, why a retry is needed — for the final status
        self.reason_detail: Text = self.reason  # in detail — for the log and the tooltip

    # --- attempts ----------------------------------------------------------------------------------

    def run(self) -> Result:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if attempt > 1:
                self._progress(t("Retry in {seconds} s", seconds=RETRY_PAUSE))
                self.sleep(RETRY_PAUSE)
                found = self._poll()  # the sent transaction may have got into a block during these 10 s
                if found is not None:
                    result = self._settle(*found)
                    if result is not None:
                        return result
                    self._log(self.reason_detail, "warn")
            self.marks.append(ACTIVE)
            self._progress(t("Sending…"))
            try:
                result = self._attempt(attempt)
            except _Fatal as exc:
                self._log(exc.detail, "error")
                return self._finish(Outcome.ERROR, t("Error: {reason}", reason=exc.status), exc.detail, FAIL)
            except _Skip as exc:
                if self.sent_any:  # transactions were already sent — so this is an error, not a skip
                    self._log(exc.detail, "error")
                    return self._finish(Outcome.ERROR, t("Error: {reason}", reason=exc.status), exc.detail, FAIL)
                self._log(t("skipped: {detail}", detail=exc.detail), "muted")
                self.marks.clear()
                return Result(Outcome.SKIPPED, t("Skipped: {reason}", reason=exc.status), exc.detail, sent=False)
            except ChainError as exc:
                self._set_reason(exc)
                result = None
            if result is not None:
                return result
            self.marks[-1] = RETRY
            if attempt < MAX_ATTEMPTS:
                self._log(t("{reason}; retry in {seconds} s (attempt {attempt}/{total})", reason=self.reason_detail,
                            seconds=RETRY_PAUSE, attempt=attempt, total=MAX_ATTEMPTS), "warn")
            else:
                self._log(t("{reason} (attempt {attempt}/{total})", reason=self.reason_detail, attempt=attempt,
                            total=MAX_ATTEMPTS), "warn")
        if self.inflight:
            detail = t("The transaction was sent but did not get into a block in {count} attempts. It may still go "
                       "through — check it by the link.", count=MAX_ATTEMPTS)
            self._log(t("not confirmed in {count} attempts, tx {tx} may still go through later", count=MAX_ATTEMPTS,
                        tx=self.last_hash), "warn")
            return self._finish(Outcome.UNCONFIRMED, t("Not confirmed"), detail, WARN)
        self._log(t("error after {count} attempts: {reason}", count=MAX_ATTEMPTS, reason=self.reason_detail), "error")
        return self._finish(Outcome.ERROR, t("Error: {reason}", reason=self.reason), self.reason_detail, FAIL)

    def _attempt(self, attempt: int) -> Result | None:
        """One attempt. A Result — the wallet is done; None — a retry is needed."""
        unsent = next((sent for sent in self.inflight if not sent.broadcast), None)
        if unsent is not None:
            # The RPC did not confirm it got the transaction — send the same signed one, its hash does not change
            self._log(t("resending the same transaction {tx} (attempt {attempt}/{total})", tx=unsent.tx_hash,
                        attempt=attempt, total=MAX_ATTEMPTS))
            self._broadcast(unsent)
        elif self.inflight:
            draft = self._replacement()
            if draft is None:
                self._log(t("not enough funds for a replacement with a higher gas price, waiting for the sent "
                            "transaction"), "warn")
            else:
                self._send(draft, attempt, replacement=True)
        else:
            self._send(self._prepare(), attempt, replacement=False)
        self._progress(t("Waiting for confirmation"))
        found = self._wait()
        if found is None:
            self.reason = t("not mined")
            self.reason_detail = t("did not get into a block in {seconds} s", seconds=self.plan.tx_timeout)
            return None
        return self._settle(*found)

    # --- preparing -----------------------------------------------------------------------------------

    def _prepare(self) -> _Draft:
        """A new transaction: fresh nonce, balances and gas price (spec 5.5, step 1)."""
        sender = self.wallet.sender
        latest, pending = self.chain.nonces(sender)
        for _ in range(PENDING_CHECKS):
            if pending <= latest:
                break
            self.sleep(PENDING_PAUSE)
            latest, pending = self.chain.nonces(sender)
        if pending > latest:
            raise _Skip(t("pending transaction"),
                        t("The wallet already has an unconfirmed transaction (nonce {nonce}). Wait for it or cancel "
                          "it and start again.", nonce=latest))
        nonce = latest  # an RPC behind a load balancer sometimes gives pending lower than latest — take the larger
        fees = self.chain.fees(self.plan.gas_multiplier).at_least(self.min_fees)
        native = self.chain.native_balance(sender)
        if self.token.native:
            return self._prepare_native(nonce, native, fees)
        return self._prepare_token(nonce, native, fees)

    def _prepare_native(self, nonce: int, balance: int, fees: Fees) -> _Draft:
        symbol, recipient = self.network.symbol, self.wallet.recipient
        if balance == 0:
            raise _Skip(t("zero balance"), t("The wallet has 0 {token}", token=symbol))
        gas = self._estimate(recipient, balance, b"")
        reserve = self._reserve(nonce, recipient, balance, b"", gas, fees)
        available = balance - reserve
        if available <= 0:
            raise _Skip(t("low {symbol} for gas", symbol=symbol),
                        t("Not enough {symbol} for gas: have {have}, need ~{need}", symbol=symbol,
                          have=human(balance, 18), need=human(reserve, 18)))
        amount = self._amount(available, after_gas=True)
        return _Draft(nonce, recipient, amount, b"", gas, fees, amount)

    def _prepare_token(self, nonce: int, native: int, fees: Fees) -> _Draft:
        symbol, label = self.network.symbol, self.token.label
        balance = self.chain.token_balance(self.token.address, self.wallet.sender)
        if balance == 0:
            raise _Skip(t("zero balance"), t("The wallet has 0 {token}", token=label))
        amount = self._amount(balance)
        data = transfer_data(self.wallet.recipient, amount)
        gas = self._estimate(self.token.address, 0, data)
        reserve = self._reserve(nonce, self.token.address, 0, data, gas, fees)
        if native < reserve:
            raise _Skip(t("low {symbol} for gas", symbol=symbol),
                        t("Not enough {symbol} for gas: have {have}, need ~{need}", symbol=symbol,
                          have=human(native, 18), need=human(reserve, 18)))
        return _Draft(nonce, self.token.address, 0, data, gas, fees, amount)

    def _amount(self, available: int, *, after_gas: bool = False) -> int:
        """The amount to send by the mode from the settings (spec 5.3)."""
        label, decimals = self.token.label, self.token.decimals
        if self.plan.amount_mode == "all":
            amount = available
        elif self.plan.amount_mode == "percent":
            with localcontext() as ctx:
                ctx.prec = 100
                amount = int((Decimal(available) * self.plan.percent / 100).to_integral_value(rounding=ROUND_FLOOR))
        else:
            if self.range_amount is None:
                self.range_amount = self._pick_range()
            amount = self.range_amount
            if amount > available:
                if available >= to_raw(self.plan.range_min, decimals):
                    amount = available  # the balance falls into the range — send all of it
                else:
                    have = human(available, decimals)
                    have = (t("{amount} {token} after gas", amount=have, token=label) if after_gas
                            else t("{amount} {token}", amount=have, token=label))
                    raise _Skip(t("below the minimum"),
                                t("Balance {have} is below the range minimum {minimum} {token}", have=have,
                                  minimum=plain(self.plan.range_min), token=label))
        if amount <= 0:
            raise _Skip(t("zero balance"), t("Nothing to send: 0 {token}", token=label))
        return amount

    def _pick_range(self) -> int:
        """A random amount from min to max, rounded down to 4 decimal places, in the token's smallest units."""
        decimals = self.token.decimals
        places = min(RANGE_DECIMALS, decimals)
        scale = Decimal(10) ** places
        low = int((self.plan.range_min * scale).to_integral_value(rounding=ROUND_CEILING))
        high = int((self.plan.range_max * scale).to_integral_value(rounding=ROUND_FLOOR))
        if low > high:  # the range has no number with 4 decimal places — take the lower bound as is
            return to_raw(self.plan.range_min, decimals)
        return self.rng.randint(low, high) * 10 ** (decimals - places)

    def _estimate(self, to: str, value: int, data: bytes) -> int:
        try:
            return self.chain.estimate_gas(self.wallet.sender, to, value, data)
        except ChainError as exc:
            if exc.kind == ChainError.INSUFFICIENT_FUNDS and value:
                # some nodes want money for gas too when estimating — estimate the same transfer without the amount
                return self.chain.estimate_gas(self.wallet.sender, to, 0, data)
            if exc.kind == ChainError.REVERTED:
                raise _Fatal(t("transfer reverted"),
                             t("Gas estimation showed the transfer will be rejected: {error}",
                               error=exc.message)) from exc
            raise

    def _reserve(self, nonce: int, to: str, value: int, data: bytes, gas: int, fees: Fees) -> int:
        """How much of the network coin may go to gas: limit × price, plus the L1 fee in Optimism and Base."""
        reserve = gas * fees.max_fee
        if self.network.l1_fee:
            raw, _ = self._sign(_Draft(nonce, to, value, data, gas, fees, 0))
            l1 = Decimal(self.chain.l1_fee(raw)) * self.plan.gas_multiplier
            reserve += int(l1.to_integral_value(rounding=ROUND_CEILING))
        return reserve

    def _replacement(self) -> _Draft | None:
        """The same transaction with the same nonce and a higher gas price. None — not enough funds for it."""
        last = self.inflight[-1]
        fees = (self.chain.fees(self.plan.gas_multiplier)
                .at_least(self.last_fees.bumped(BUMP) if self.last_fees else None)
                .at_least(self.min_fees))
        native = self.chain.native_balance(self.wallet.sender)
        if self.token.native:
            recipient = self.wallet.recipient
            reserve = self._reserve(last.nonce, recipient, last.value, b"", last.gas, fees)
            if self.plan.amount_mode == "all":
                value = native - reserve  # "whole balance": the amount shrinks by the fee increase
                if value <= 0:
                    return None
            else:
                value = last.value
                if value + reserve > native:
                    return None
            return _Draft(last.nonce, recipient, value, b"", last.gas, fees, value)
        data = transfer_data(self.wallet.recipient, last.amount)
        reserve = self._reserve(last.nonce, self.token.address, 0, data, last.gas, fees)
        if native < reserve:
            return None
        return _Draft(last.nonce, self.token.address, 0, data, last.gas, fees, last.amount)

    # --- sending and receipts ------------------------------------------------------------------------

    def _sign(self, draft: _Draft) -> tuple[bytes, str]:
        tx = {
            "chainId": self.network.chain_id,
            "nonce": draft.nonce,
            "to": draft.to,
            "value": draft.value,
            "data": draft.data,
            "gas": draft.gas,
            **draft.fees.tx_fields(),
        }
        signed = Account.sign_transaction(tx, self.wallet.private_key)
        return bytes(signed.raw_transaction), "0x" + bytes(signed.hash).hex()

    def _send(self, draft: _Draft, attempt: int, *, replacement: bool) -> None:
        raw, tx_hash = self._sign(draft)
        sent = _Sent(tx_hash, raw, draft.nonce, draft.fees, draft.gas, draft.value, draft.amount)
        self.last_fees = draft.fees
        action = t("replacement with the same nonce") if replacement else t("sending")
        self._log(t("{action} {amount} {token} → {to}, gas {gwei} gwei, attempt {attempt}/{total}", action=action,
                    amount=human(draft.amount, self.token.decimals), token=self.token.label,
                    to=short_address(self.wallet.recipient), gwei=gwei(draft.fees.max_fee), attempt=attempt,
                    total=MAX_ATTEMPTS))
        self.inflight.append(sent)
        self._broadcast(sent)
        if sent.broadcast:
            self._log(t("tx {tx} sent", tx=tx_hash))

    def _broadcast(self, sent: _Sent) -> None:
        """Sending to the network. It counts as accepted only if the node returned the same hash (spec 5.5, step 2)."""
        self.sent_any = True
        try:
            returned = self.chain.send_raw(sent.raw)
        except ChainError as exc:
            if exc.kind == ChainError.ALREADY_KNOWN:  # the node already knows this transaction — it is in the network
                sent.broadcast = True
                self.last_hash = sent.tx_hash
                return
            if exc.kind == ChainError.RPC:
                sent.uncertain = True  # whether it was accepted is unknown; the next attempt sends the same one
                self.last_hash = sent.tx_hash
                raise
            if sent.uncertain:
                # The connection broke on this very transaction before — it may be in the network or even in a block
                # (then the node answers "nonce too low"). No new transaction: wait for this one's receipt.
                sent.broadcast = True
                self._log(t("the node answered “{error}”; the transaction may already be in the network — waiting for "
                            "its receipt", error=exc.message), "warn")
                return
            self.inflight.remove(sent)  # the node definitely rejected the transaction, it is not in the network
            if exc.kind == ChainError.UNDERPRICED:
                self.min_fees = sent.fees.bumped(BUMP)
                raise
            if exc.kind == ChainError.NONCE_TOO_LOW and self.inflight:
                # the nonce is taken — most likely by our own previous transaction: wait for its receipt
                self._log(t("the nonce is already taken, checking the transaction sent earlier"), "warn")
                return
            if exc.kind == ChainError.INSUFFICIENT_FUNDS:
                if self.inflight:
                    self._log(t("not enough funds for a replacement, waiting for the sent transaction"), "warn")
                    return
                raise _Fatal(t("insufficient funds"),
                             t("The node rejected the transaction: insufficient funds ({error})",
                               error=exc.message)) from exc
            raise
        if returned.lower() != sent.tx_hash.lower():
            raise ChainError(ChainError.RPC, t("the RPC returned a different transaction hash: {hash}", hash=returned))
        sent.broadcast = True
        self.last_hash = sent.tx_hash

    def _wait(self) -> tuple[_Sent, dict] | None:
        """Waits for a receipt of any of the sent transactions until the timeout from the settings."""
        if not self.inflight:
            return None
        deadline = self.clock() + self.plan.tx_timeout
        while True:
            found = self._poll()
            if found is not None:
                return found
            if self.clock() >= deadline:
                return None
            self.sleep(POLL_INTERVAL)

    def _poll(self) -> tuple[_Sent, dict] | None:
        for sent in reversed(self.inflight):
            try:
                receipt = self.chain.receipt(sent.tx_hash)
            except ChainError:
                continue  # a temporary RPC error — ask again later
            if receipt is not None:
                return sent, receipt
        return None

    def _settle(self, sent: _Sent, receipt: dict) -> Result | None:
        """The receipt is here (spec 5.5, step 4). None — the transaction failed, retry with a new nonce."""
        self.inflight.clear()
        self.last_hash = sent.tx_hash
        block = receipt.get("block")
        if receipt["status"] != 1:
            self.reason = t("transaction failed")
            self.reason_detail = t("tx {tx} got into block {block} but failed (status 0)", tx=sent.tx_hash, block=block)
            return None
        amount = f"{human(sent.amount, self.token.decimals)} {self.token.label}"
        if not self.token.native:
            moved = find_transfer(receipt, self.token.address, self.wallet.sender, self.wallet.recipient)
            if moved != sent.amount:
                if moved is None:
                    detail = t("The transaction went through, but the Transfer event to the recipient was not found")
                else:
                    detail = t("The transaction went through, but the Transfer event has {moved} {token} instead of "
                               "{amount}", moved=human(moved, self.token.decimals), token=self.token.label,
                               amount=amount)
                self._log(t("{detail}; block {block}, tx {tx}. Needs review", detail=detail, block=block,
                            tx=sent.tx_hash), "warn")
                return self._finish(Outcome.CHECK, t("Needs review"), detail, WARN)
        self._log(t("success, block {block}, tx {tx}", block=block, tx=sent.tx_hash), "ok")
        return self._finish(Outcome.OK, t("Success: {amount}", amount=amount),
                            t("Sent {amount}, block {block}", amount=amount, block=block), OK_MARK)

    # --- helpers ---------------------------------------------------------------------------------------

    def _set_reason(self, exc: ChainError) -> None:
        error = exc.message
        if exc.kind == ChainError.NONCE_TOO_LOW:
            self.reason = t("nonce already used")
            self.reason_detail = t("nonce already used ({error}), taking a new one", error=error)
        elif exc.kind == ChainError.UNDERPRICED:
            self.reason = t("gas price too low")
            self.reason_detail = t("the node rejected the gas price as too low ({error}), raising it by 15%",
                                   error=error)
        elif exc.kind == ChainError.INSUFFICIENT_FUNDS:
            self.reason, self.reason_detail = t("insufficient funds"), t("insufficient funds ({error})", error=error)
        elif exc.kind == ChainError.REVERTED:
            self.reason = t("call reverted")
            self.reason_detail = t("the contract rejects the call ({error})", error=error)
        elif exc.kind == ChainError.REJECTED:
            self.reason, self.reason_detail = t("rejected by the node"), t("the node rejected: {error}",
                                                                                        error=error)
        else:
            self.reason, self.reason_detail = t("RPC not responding"), t("RPC error: {error}", error=error)

    def _finish(self, outcome: Outcome, status: Text, detail: Text, mark: str) -> Result:
        if self.marks:
            self.marks[-1] = mark
        else:
            self.marks.append(mark)
        return Result(outcome, status, detail, sent=self.sent_any, tx_hash=self.last_hash, marks=list(self.marks))

    def _progress(self, status: Text) -> None:
        self.reporter.progress(status, list(self.marks), self.last_hash)

    def _log(self, text: Text, level: str = "info") -> None:
        self.reporter.log(text, level)


# --- the mailing ---------------------------------------------------------------------------------------


class Events(Protocol):
    """Where the logic reports the progress of the mailing: the program window or a test."""

    def update(self, row: int, changes: dict) -> None: ...

    def log(self, text: Text, level: str = "info") -> None: ...

    def progress(self, done: int, total: int, text: Text) -> None: ...


@dataclass(frozen=True)
class Job:
    row: int  # the table row
    wallet: WalletEntry


def wallet_prefix(wallet: WalletEntry) -> Text:
    """How a wallet starts its lines in the log: "#3 Main 1"."""
    return t("#{num} {name}", num=wallet.num, name=wallet.title)


class _RowReporter:
    def __init__(self, events: Events, job: Job) -> None:
        self.events = events
        self.job = job
        self.prefix = wallet_prefix(job.wallet)

    def progress(self, status: Text, marks: list[str], tx_hash: str | None) -> None:
        self.events.update(self.job.row, {"state": "sending", "status": status, "detail": None,
                                          "marks": marks, "tx_hash": tx_hash})

    def log(self, text: Text, level: str = "info") -> None:
        self.events.log(t("{prefix}: {text}", prefix=self.prefix, text=text), level)


class Mailing:
    """The whole mailing: the checked wallets one by one, delays between them, the Stop button (spec 5.8)."""

    def __init__(self, chain, network: Network, token: Token, plan: Plan, jobs: list[Job], events: Events,
                 stop: threading.Event, *, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, wait: Callable[[float], bool] | None = None,
                 rng: random.Random | None = None) -> None:
        self.chain = chain
        self.network = network
        self.token = token
        self.plan = plan
        self.jobs = jobs
        self.events = events
        self.stop = stop
        self.sleep = sleep
        self.clock = clock
        self.wait = wait or stop.wait  # an interruptible wait: True — Stop was pressed
        self.rng = rng or random.Random()

    def run(self) -> Counter:
        jobs = list(self.jobs)
        if self.plan.order == "random":
            self.rng.shuffle(jobs)
        total = len(jobs)
        order = t("random order") if self.plan.order == "random" else t("file order")
        self.events.log(t("Sending started: {network}, {token}, {count:wallets}, {order}", network=self.network.title,
                          token=self.token.label, count=total, order=order))
        counts: Counter = Counter()
        for index, job in enumerate(jobs):
            if self.stop.is_set():
                self._mark_stopped(jobs[index:], counts)
                break
            self.events.progress(index, total, t("Processed {done} of {total}, now {wallet}", done=index, total=total,
                                                 wallet=wallet_prefix(job.wallet)))
            result = self._process(job)
            counts[result.outcome] += 1
            self.events.update(job.row, {"state": result.outcome.value, "status": result.status,
                                         "detail": result.detail, "marks": result.marks, "tx_hash": result.tx_hash})
            self._refresh_balances(job)
            self.events.progress(index + 1, total, t("Processed {done} of {total}", done=index + 1, total=total))
            if result.sent and index < total - 1 and self._pause(index + 1, total):
                self._mark_stopped(jobs[index + 1:], counts)
                break
        bad = counts[Outcome.ERROR] + counts[Outcome.UNCONFIRMED] + counts[Outcome.CHECK]
        self.events.log(self._summary(counts), "warn" if bad else "ok")
        return counts

    def _process(self, job: Job) -> Result:
        sender = WalletSender(self.chain, self.network, self.token, self.plan, job.wallet,
                              _RowReporter(self.events, job), sleep=self.sleep, clock=self.clock, rng=self.rng)
        try:
            return sender.run()
        except Exception as exc:  # noqa: BLE001 — a failure of one wallet must not stop the mailing
            detail = t("Unexpected error: {error}", error=str(exc))
            self.events.log(t("{prefix}: {text}", prefix=wallet_prefix(job.wallet), text=detail), "error")
            outcome = Outcome.UNCONFIRMED if sender.inflight else Outcome.ERROR
            status = t("Not confirmed") if sender.inflight else t("Error: {reason}", reason=t("unexpected error"))
            return Result(outcome, status, detail, sent=sender.sent_any, tx_hash=sender.last_hash,
                          marks=sender.marks[:-1] + [FAIL] if sender.marks else [])

    def _pause(self, done: int, total: int) -> bool:
        """A random delay between wallets with a countdown. True — Stop was pressed."""
        seconds = self.rng.randint(self.plan.delay_min, self.plan.delay_max)
        if seconds <= 0:
            return self.stop.is_set()
        self.events.log(t("Delay {seconds} s", seconds=seconds), "muted")
        end = self.clock() + seconds
        while (left := end - self.clock()) > 0:
            self.events.progress(done, total, t("Processed {done} of {total}, delay {seconds} s", done=done,
                                                total=total, seconds=math.ceil(left)))
            if self.wait(min(1.0, left)):
                return True
        return False

    def _mark_stopped(self, jobs: list[Job], counts: Counter) -> None:
        for job in jobs:
            self.events.update(job.row, {"state": "stopped", "status": t("Not processed (stopped)"),
                                         "detail": t("Sending was stopped with the Stop button"), "marks": [],
                                         "tx_hash": None})
        counts[Outcome.STOPPED] += len(jobs)
        if jobs:
            self.events.log(t("Sending stopped, not processed: {count:wallets}", count=len(jobs)), "warn")

    def _refresh_balances(self, job: Job) -> None:
        """After a wallet is processed, its balances in the table are refreshed (spec 5.2)."""
        try:
            native = self.chain.native_balance(job.wallet.sender)
            token = native if self.token.native else self.chain.token_balance(self.token.address, job.wallet.sender)
        except ChainError:
            return
        self.events.update(job.row, {"native_balance": from_raw(native, 18),
                                     "token_balance": from_raw(token, self.token.decimals)})

    @staticmethod
    def _summary(counts: Counter) -> Text:
        values = {"ok": counts[Outcome.OK], "check": counts[Outcome.CHECK], "unconfirmed": counts[Outcome.UNCONFIRMED],
                  "error": counts[Outcome.ERROR], "skipped": counts[Outcome.SKIPPED]}
        if counts[Outcome.STOPPED]:
            return t("Done: {ok} succeeded, {check} need review, {unconfirmed} not confirmed, {error} failed, "
                     "{skipped} skipped, {stopped} not processed", stopped=counts[Outcome.STOPPED], **values)
        return t("Done: {ok} succeeded, {check} need review, {unconfirmed} not confirmed, {error} failed, "
                 "{skipped} skipped", **values)
