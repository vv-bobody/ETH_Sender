"""A network in memory for tests: a script decides what the node does with every sent transaction."""
from __future__ import annotations

import threading
from collections import Counter

import rlp
from eth_account import Account
from eth_utils import keccak

from app.chain import TRANSFER_TOPIC, ChainError, Fees, _mul


class FakeClock:
    """Time that only moves while the program "sleeps" — the tests never really wait."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _int(value: bytes) -> int:
    return int.from_bytes(value, "big")


def decode_tx(raw: bytes) -> dict:
    if raw[0] == 2:
        _, nonce, tip, max_fee, gas, to, value, data = rlp.decode(raw[1:])[:8]
        return {"type": 2, "nonce": _int(nonce), "priority_fee": _int(tip), "max_fee": _int(max_fee),
                "gas": _int(gas), "to": "0x" + to.hex(), "value": _int(value), "data": data}
    nonce, gas_price, gas, to, value, data = rlp.decode(raw)[:6]
    return {"type": 0, "nonce": _int(nonce), "priority_fee": 0, "max_fee": _int(gas_price), "gas": _int(gas),
            "to": "0x" + to.hex(), "value": _int(value), "data": data}


class FakeChain:
    """Actions for the next sends are set in script:
    mine — gets into a block, fail — into a block with status 0, hang — hangs forever,
    rpc — the connection broke before the node, rpc_accepted — the node accepted it, but the answer got lost,
    known — "already known", underpriced, insufficient, nonce_low — refusals of the node.

    rate_limit = (count, seconds) — balance requests above count per seconds get "too many requests";
    fail_for — addresses whose balance requests fail.
    """

    def __init__(self, clock: FakeClock, *, native: int = 10**18, token: int = 0, token_address: str | None = None,
                 legacy: bool = False, base_fee: int = 100, tip: int = 10, gas: int = 21000, l1_fee: int = 0,
                 nonce: int = 0, pending_nonce: int | None = None, mine_after: float = 4, chain_id: int = 42161) -> None:
        self.clock = clock
        self.native = native
        self.native_by: dict[str, int] = {}
        self.token = token
        self.token_by: dict[str, int] = {}
        self.token_address = token_address
        self.legacy = legacy
        self.base_fee = base_fee
        self.tip = tip
        self.gas = gas
        self.l1 = l1_fee
        self.nonce = nonce
        self.pending_nonce = pending_nonce
        self.mine_after = mine_after
        self.id = chain_id
        self.code = True
        self.symbol, self.decimals = "USDC", 6
        self.script: list[str] = []
        self.sent: list[dict] = []
        self.receipts: dict[str, tuple[float, dict, int]] = {}
        self.failures: Counter = Counter()  # method → how many times in a row to answer "no connection"
        self.estimate_error: ChainError | None = None
        self.transfer_event = True
        self.transfer_delta = 0  # how much the Transfer amount differs from the sent one
        self.estimates: list[int] = []
        self.rate_limit: tuple[int, float] | None = None
        self.limited = 0  # how many requests got "too many requests"
        self.fail_for: set[str] = set()
        self._recent: list[float] = []
        self._lock = threading.Lock()

    def _maybe_fail(self, method: str) -> None:
        if self.failures[method] > 0:
            self.failures[method] -= 1
            raise ChainError(ChainError.RPC, "no connection to the RPC")

    def _balance_request(self, address: str) -> None:
        """Balance requests are where rate limits and failures for single wallets are simulated."""
        if address in self.fail_for:
            raise ChainError(ChainError.RPC, "no connection to the RPC")
        if self.rate_limit is None:
            return
        count, seconds = self.rate_limit
        with self._lock:
            now = self.clock()
            self._recent = [moment for moment in self._recent if moment > now - seconds]
            if len(self._recent) >= count:
                self.limited += 1
                raise ChainError(ChainError.RPC, "429 Too Many Requests", rate_limited=True)
            self._recent.append(now)

    def chain_id(self) -> int:
        self._maybe_fail("chain_id")
        return self.id

    def has_code(self, address: str) -> bool:
        return self.code

    def token_info(self, address: str) -> tuple[str, int]:
        return self.symbol, self.decimals

    def _advance_nonce(self) -> None:
        """As in a real network: the nonce grows when a transaction gets into a block, even if nobody asked for the receipt."""
        for ready_at, _, nonce in self.receipts.values():
            if self.clock() >= ready_at:
                self.nonce = max(self.nonce, nonce + 1)

    def nonces(self, address: str) -> tuple[int, int]:
        self._maybe_fail("nonces")
        self._advance_nonce()
        return self.nonce, self.pending_nonce if self.pending_nonce is not None else self.nonce

    def native_balance(self, address: str) -> int:
        self._maybe_fail("native_balance")
        self._balance_request(address)
        return self.native_by.get(address, self.native)

    def token_balance(self, token: str, address: str) -> int:
        self._maybe_fail("token_balance")
        self._balance_request(address)
        return self.token_by.get(address, self.token)

    def fees(self, multiplier) -> Fees:
        self._maybe_fail("fees")
        if self.legacy:
            return Fees(True, _mul(self.base_fee + self.tip, multiplier))
        return Fees(False, _mul(self.base_fee + self.tip, multiplier), _mul(self.tip, multiplier))

    def estimate_gas(self, sender: str, to: str, value: int, data: bytes) -> int:
        self._maybe_fail("estimate_gas")
        self.estimates.append(value)
        if self.estimate_error is not None:
            raise self.estimate_error
        return self.gas

    def l1_fee(self, raw: bytes) -> int:
        return self.l1

    def send_raw(self, raw: bytes) -> str:
        self._maybe_fail("send_raw")
        tx = decode_tx(raw)
        tx_hash = "0x" + keccak(raw).hex()
        action = self.script.pop(0) if self.script else "mine"
        self.sent.append({"hash": tx_hash, "action": action, "raw": raw, **tx})
        refusals = {
            "underpriced": (ChainError.UNDERPRICED, "replacement transaction underpriced"),
            "insufficient": (ChainError.INSUFFICIENT_FUNDS, "insufficient funds for gas * price + value"),
            "nonce_low": (ChainError.NONCE_TOO_LOW, "nonce too low"),
            "nonce_used": (ChainError.NONCE_TOO_LOW, "nonce too low"),  # the nonce is taken, but not by a foreign tx
            "rejected": (ChainError.REJECTED, "intrinsic gas too low"),
        }
        if action == "rpc":
            raise ChainError(ChainError.RPC, "no connection to the RPC")
        if action == "rpc_accepted":
            self._mine(raw, tx_hash, tx, status=1)
            raise ChainError(ChainError.RPC, "no connection to the RPC")
        if action == "known":
            self._mine(raw, tx_hash, tx, status=1)
            raise ChainError(ChainError.ALREADY_KNOWN, "already known")
        if action in refusals:
            if action == "nonce_low":
                self.nonce += 1  # a foreign transaction took the nonce
            raise ChainError(*refusals[action])
        if action in ("mine", "fail"):
            self._mine(raw, tx_hash, tx, status=1 if action == "mine" else 0)
        return tx_hash

    def _mine(self, raw: bytes, tx_hash: str, tx: dict, *, status: int) -> None:
        logs = []
        data = tx["data"]
        if self.token_address and data and status == 1 and self.transfer_event:
            sender = Account.recover_transaction(raw)
            amount = _int(data[36:68]) + self.transfer_delta
            logs.append({
                "address": self.token_address,
                "topics": [TRANSFER_TOPIC, bytes(12) + bytes.fromhex(sender[2:]), bytes(12) + data[16:36]],
                "data": amount.to_bytes(32, "big"),
            })
        receipt = {"status": status, "block": 1000 + len(self.receipts), "logs": logs}
        self.receipts[tx_hash] = (self.clock() + self.mine_after, receipt, tx["nonce"])

    def receipt(self, tx_hash: str) -> dict | None:
        self._maybe_fail("receipt")
        entry = self.receipts.get(tx_hash)
        if entry is None or self.clock() < entry[0]:
            return None
        _, receipt, nonce = entry
        self.nonce = max(self.nonce, nonce + 1)
        return receipt
