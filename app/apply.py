"""Apply (spec 5.1–5.2): checking the RPC and the token, polling balances with retries and rate limits (spec 12.5)."""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.addresses import checksum
from app.chain import ChainError
from app.i18n import Text, t
from app.networks import Network
from app.sender import Token
from app.settings import NATIVE
from app.units import from_raw
from app.wallets import WalletEntry

POLL_WORKERS = 5  # requests at once, at most
POLL_TRIES = 3  # attempts per request on ordinary errors: no connection, a timeout
POLL_PAUSE = 1.0  # sec between those attempts
LIMIT_BACKOFF = (1, 2, 4, 8)  # sec to wait after "too many requests": up to 5 attempts in total
RAISE_AFTER = 20  # successful requests in a row after which one more request may run at once


class ApplyError(Exception):
    """The settings cannot be applied: the RPC does not answer, it is another network or there is no contract."""

    def __init__(self, message: Text) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return str(self.message)


def check_rpc(chain, network: Network) -> None:
    try:
        chain_id = chain.chain_id()
    except ChainError as exc:
        raise ApplyError(t("The {network} RPC does not respond: {error}", network=network.title,
                           error=exc.message)) from exc
    if chain_id != network.chain_id:
        raise ApplyError(t("The {network} RPC returned chain ID {got}, expected {expected}. Check the RPC address.",
                           network=network.title, got=chain_id, expected=network.chain_id))


def resolve_token(chain, network: Network, token_setting: str) -> Token:
    """The token from the settings: the native coin, a ready-made stablecoin or a contract by address."""
    if token_setting == NATIVE:
        return Token(None, 18, network.symbol)
    preset = network.preset(token_setting)
    address = preset.address if preset else checksum(token_setting)
    try:
        if not chain.has_code(address):
            raise ApplyError(t("There is no contract at {address} in {network}. Check the token address and the "
                               "selected network.", address=address, network=network.title))
        symbol, decimals = chain.token_info(address)
    except ChainError as exc:
        raise ApplyError(t("Could not read the token {address}: {error}", address=address, error=exc.message)) from exc
    return Token(address, decimals, preset.label if preset else symbol)


class Throttle:
    """Shared by all polling threads (spec 12.5): how many requests may run at once and when the RPC may be asked
    again. The RPC counts the requests of the whole program, so the pause after a rate limit holds back all of them."""

    def __init__(self, workers: int = POLL_WORKERS, *, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.workers = workers
        self.limit = workers  # requests allowed at once right now
        self.active = 0
        self.resume_at = 0.0  # the RPC may be asked again from this moment
        self.streak = 0  # successful requests in a row
        self.clock = clock
        self.sleep = sleep
        self._cond = threading.Condition()

    def acquire(self) -> None:
        with self._cond:
            while self.active >= self.limit:
                self._cond.wait(0.05)
            self.active += 1
        while True:
            with self._cond:
                delay = self.resume_at - self.clock()
            if delay <= 0:
                return
            self.sleep(delay)

    def release(self, ok: bool) -> None:
        with self._cond:
            self.active -= 1
            self.streak = self.streak + 1 if ok else 0
            if self.streak >= RAISE_AFTER and self.limit < self.workers:
                self.limit += 1
                self.streak = 0
            self._cond.notify_all()

    def limited(self, attempt: int) -> int:
        """The RPC said "too many requests": half as many requests at once and a pause for all of them."""
        delay = LIMIT_BACKOFF[attempt]
        with self._cond:
            self.limit = max(1, self.limit // 2)
            self.streak = 0
            self.resume_at = max(self.resume_at, self.clock() + delay)
        return delay


def poll_balances(chain, token: Token, jobs: list[tuple[int, WalletEntry]],
                  on_row: Callable[[int, dict], None], on_progress: Callable[[int, int], None], *,
                  on_limit: Callable[[int], None] | None = None, workers: int = POLL_WORKERS,
                  tries: int = POLL_TRIES, pause: float = POLL_PAUSE, sleep: Callable[[float], None] = time.sleep,
                  clock: Callable[[], float] = time.monotonic) -> int:
    """Polls the balances in parallel; returns for how many wallets polling failed.
    on_limit(seconds) — the RPC limits the request rate and polling waits that long."""
    throttle = Throttle(workers, clock=clock, sleep=sleep)

    def call(request):
        limited = failures = 0
        while True:
            throttle.acquire()
            try:
                value = request()
            except ChainError as exc:
                throttle.release(ok=False)
                if exc.rate_limited:
                    if limited >= len(LIMIT_BACKOFF):
                        raise
                    delay = throttle.limited(limited)
                    limited += 1
                    if on_limit is not None:
                        on_limit(delay)
                    continue
                failures += 1
                if failures >= tries:
                    raise
                sleep(pause)
                continue
            throttle.release(ok=True)
            return value

    def fetch(row: int, wallet: WalletEntry) -> tuple[int, dict]:
        try:
            native = call(lambda: chain.native_balance(wallet.sender))
            raw = native if token.native else call(lambda: chain.token_balance(token.address, wallet.sender))
        except ChainError as exc:
            return row, {"balance_error": exc.message}
        return row, {"native_balance": from_raw(native, 18), "token_balance": from_raw(raw, token.decimals)}

    failed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch, row, wallet) for row, wallet in jobs]
        for done, future in enumerate(as_completed(futures), start=1):
            row, changes = future.result()
            failed += "balance_error" in changes
            on_row(row, changes)
            on_progress(done, len(jobs))
    return failed
