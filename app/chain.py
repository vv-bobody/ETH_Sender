"""Talking to the network over RPC (spec 5.1–5.4, 12.5): chain ID, token, balances, gas, sending, receipts."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

import re

import requests
from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from web3 import HTTPProvider, Web3
from web3.exceptions import ContractLogicError, TransactionNotFound, Web3RPCError
from web3.middleware import ExtraDataToPOAMiddleware

from app.i18n import Text, t
from app.networks import Network

GAS_PRICE_ORACLE = "0x420000000000000000000000000000000000000F"  # OP Stack: calculates the L1 fee
TRANSFER_TOPIC = bytes(Web3.keccak(text="Transfer(address,address,uint256)"))
RPC_TIMEOUT = 20  # sec per request (spec 7)

# How nodes say "too many requests" besides HTTP 429 (spec 12.5): Infura -32005, public OP Stack RPCs -32016,
# Alchemy puts 429 into the JSON-RPC error
RATE_LIMIT_CODES = frozenset({-32005, -32016, 429})
RATE_LIMIT_WORDS = ("rate limit", "too many requests", "limit exceeded", "rate exceeded", "request limit")
_ERROR_CODE = re.compile(r"""['"]code['"]\s*:\s*(-?\d+)""")


def _selector(signature: str) -> bytes:
    return bytes(Web3.keccak(text=signature)[:4])


SEL_BALANCE_OF = _selector("balanceOf(address)")
SEL_TRANSFER = _selector("transfer(address,uint256)")
SEL_DECIMALS = _selector("decimals()")
SEL_SYMBOL = _selector("symbol()")
SEL_GET_L1_FEE = _selector("getL1Fee(bytes)")


def transfer_data(recipient: str, amount: int) -> bytes:
    """Call data of transfer(recipient, amount) for ERC-20."""
    return SEL_TRANSFER + abi_encode(["address", "uint256"], [recipient, amount])


class ChainError(Exception):
    """A failed request to the network. Its kind decides whether a retry makes sense."""

    RPC = "rpc"  # no connection, a timeout, a rate limit — whether the request arrived is unknown; can be retried
    REJECTED = "rejected"  # the node answered with an error — a sent transaction was definitely not accepted
    INSUFFICIENT_FUNDS = "insufficient_funds"
    NONCE_TOO_LOW = "nonce_too_low"
    UNDERPRICED = "underpriced"
    ALREADY_KNOWN = "already_known"
    REVERTED = "reverted"  # the contract rejects the call

    def __init__(self, kind: str, message: Text | str, *, rate_limited: bool = False) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.rate_limited = rate_limited  # the RPC said "too many requests": wait longer before asking again

    def __str__(self) -> str:
        return str(self.message)


def _short(text: str, limit: int = 220) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _error_code(exc: BaseException) -> int | None:
    """The JSON-RPC error code from the node's answer, if there is one."""
    response = getattr(exc, "rpc_response", None)
    if isinstance(response, dict) and isinstance(response.get("error"), dict):
        code = response["error"].get("code")
        if isinstance(code, int):
            return code
    match = _ERROR_CODE.search(str(exc))
    return int(match.group(1)) if match else None


def is_rate_limit(exc: BaseException) -> bool:
    """The RPC answered "too many requests": HTTP 429, a known error code or the usual words (spec 12.5)."""
    if isinstance(exc, requests.exceptions.HTTPError):
        return exc.response is not None and exc.response.status_code == 429
    lower = str(exc).lower()
    return _error_code(exc) in RATE_LIMIT_CODES or any(word in lower for word in RATE_LIMIT_WORDS)


def classify(exc: BaseException) -> ChainError:
    """Turns a web3/requests exception into a ChainError with a clear message."""
    if isinstance(exc, ChainError):
        return exc
    if isinstance(exc, ContractLogicError):
        return ChainError(ChainError.REVERTED, _short(str(exc)))
    if isinstance(exc, requests.exceptions.Timeout):
        return ChainError(ChainError.RPC, t("the RPC did not respond within {seconds} s", seconds=RPC_TIMEOUT))
    if isinstance(exc, requests.exceptions.ConnectionError):
        return ChainError(ChainError.RPC, t("no connection to the RPC"))
    if is_rate_limit(exc):
        # A rate limit stays an RPC error: the request was not processed and may be sent again as it is
        detail = "429" if isinstance(exc, requests.exceptions.HTTPError) else _short(str(exc))
        return ChainError(ChainError.RPC, t("the RPC limits the request rate ({detail})", detail=detail),
                          rate_limited=True)
    if isinstance(exc, requests.exceptions.HTTPError):
        status = exc.response.status_code if exc.response is not None else "?"
        return ChainError(ChainError.RPC, t("the RPC returned HTTP error {status}", status=status))
    text = str(exc)
    lower = text.lower()
    if "execution reverted" in lower:  # before the others: a revert reason may say "insufficient funds"
        return ChainError(ChainError.REVERTED, _short(text))
    # Nodes word a lack of funds differently too: Geth, Erigon, Nethermind, eth-tester
    if any(marker in lower for marker in ("insufficient funds", "insufficient balance", "insufficient sender balance",
                                          "not enough balance", "does not have enough")):
        return ChainError(ChainError.INSUFFICIENT_FUNDS, _short(text))
    if "nonce too low" in lower or "nonce is too low" in lower or "already been used" in lower:
        return ChainError(ChainError.NONCE_TOO_LOW, _short(text))
    if "already known" in lower or "known transaction" in lower or "already imported" in lower:
        return ChainError(ChainError.ALREADY_KNOWN, _short(text))
    if "underpriced" in lower or "fee too low" in lower or "less than block base fee" in lower:
        return ChainError(ChainError.UNDERPRICED, _short(text))
    # Nodes describe a contract rejection differently: Geth — "execution reverted" and "invalid opcode",
    # Reth — "EVM error: …", Erigon — "VM execution error"
    if any(marker in lower for marker in ("revert", "invalid opcode", "evm error", "vm execution error",
                                          "gas required exceeds")):
        return ChainError(ChainError.REVERTED, _short(text))
    if isinstance(exc, Web3RPCError):  # the node answered, but with a refusal — e.g. "intrinsic gas too low"
        return ChainError(ChainError.REJECTED, _short(text))
    return ChainError(ChainError.RPC, _short(text) or type(exc).__name__)


def _mul(value: int, factor: Decimal) -> int:
    return int((Decimal(value) * factor).to_integral_value(rounding=ROUND_CEILING))


@dataclass(frozen=True)
class Fees:
    """Gas price. legacy — gasPrice (BSC), otherwise EIP-1559; for legacy max_fee is the gasPrice."""

    legacy: bool
    max_fee: int
    priority_fee: int = 0

    def bumped(self, factor: Decimal) -> Fees:
        return Fees(self.legacy, _mul(self.max_fee, factor), _mul(self.priority_fee, factor))

    def at_least(self, other: Fees | None) -> Fees:
        if other is None:
            return self
        return Fees(self.legacy, max(self.max_fee, other.max_fee), max(self.priority_fee, other.priority_fee))

    def tx_fields(self) -> dict:
        if self.legacy:
            return {"gasPrice": self.max_fee}
        return {"type": 2, "maxFeePerGas": self.max_fee, "maxPriorityFeePerGas": self.priority_fee}


class Chain:
    def __init__(self, network: Network, rpc_url: str, *, w3: Web3 | None = None) -> None:
        """w3 — a ready connection (for tests on a local blockchain); normally it is created from rpc_url."""
        self.network = network
        if w3 is None:
            # web3's own retries are off: the program decides when to retry (spec 5.6, 12.5)
            provider = HTTPProvider(rpc_url, request_kwargs={"timeout": RPC_TIMEOUT},
                                    exception_retry_configuration=None)
            w3 = Web3(provider)
        self.w3 = w3
        # In BSC and Avalanche the extraData of a block may be longer than 32 bytes (in Avalanche — only in some
        # blocks), and web3.py cannot read such blocks without this
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    @staticmethod
    def _call(fn, *args):
        try:
            return fn(*args)
        except Exception as exc:  # noqa: BLE001 — any network error becomes a ChainError
            raise classify(exc) from exc

    def chain_id(self) -> int:
        return self._call(lambda: self.w3.eth.chain_id)

    def _eth_call(self, to: str, data: bytes) -> bytes:
        return bytes(self._call(self.w3.eth.call, {"to": to, "data": data}))

    def has_code(self, address: str) -> bool:
        return len(self._call(self.w3.eth.get_code, address)) > 0

    def token_info(self, address: str) -> tuple[str, int]:
        """symbol() and decimals() of an ERC-20 contract."""
        decimals = int.from_bytes(self._eth_call(address, SEL_DECIMALS)[:32], "big")
        raw = self._eth_call(address, SEL_SYMBOL)
        try:
            if len(raw) == 32:  # old tokens return bytes32
                symbol = raw.rstrip(b"\0").decode("utf-8", "replace")
            else:
                symbol = abi_decode(["string"], raw)[0]
        except Exception:  # noqa: BLE001 — the symbol is only a label, the program can do without it
            symbol = "ERC-20"
        return symbol.strip() or "ERC-20", decimals

    def native_balance(self, address: str) -> int:
        return self._call(self.w3.eth.get_balance, address)

    def token_balance(self, token: str, address: str) -> int:
        data = SEL_BALANCE_OF + abi_encode(["address"], [address])
        return int.from_bytes(self._eth_call(token, data)[:32], "big")

    def nonces(self, address: str) -> tuple[int, int]:
        """The nonce by the latest block and with pending transactions counted."""
        latest = self._call(self.w3.eth.get_transaction_count, address, "latest")
        pending = self._call(self.w3.eth.get_transaction_count, address, "pending")
        return latest, pending

    def fees(self, multiplier: Decimal) -> Fees:
        """The current gas price of the network times the multiplier from the settings (spec 5.4)."""
        if not self.network.eip1559:
            return Fees(True, _mul(self._call(lambda: self.w3.eth.gas_price), multiplier))
        block = self._call(self.w3.eth.get_block, "latest")
        base = int(block.get("baseFeePerGas") or 0)
        tip = max(self._suggested_tip(), self._recent_tip())
        return Fees(False, _mul(base + tip, multiplier), _mul(tip, multiplier))

    def _suggested_tip(self) -> int:
        try:
            return int(self._call(lambda: self.w3.eth.max_priority_fee))
        except ChainError:
            return 0

    def _recent_tip(self) -> int:
        """The median tip of the last 10 blocks. Public Ethereum RPCs suggest almost zero,
        and with such a tip a transaction may hang for hours."""
        try:
            history = self._call(self.w3.eth.fee_history, 10, "latest", [50])
        except ChainError:
            return 0
        rewards = sorted(int(block[0]) for block in history.get("reward") or [] if block)
        return rewards[len(rewards) // 2] if rewards else 0

    def estimate_gas(self, sender: str, to: str, value: int, data: bytes) -> int:
        return self._call(self.w3.eth.estimate_gas, {"from": sender, "to": to, "value": value, "data": data})

    def l1_fee(self, raw_tx: bytes) -> int:
        """The L1 fee of Optimism and Base: the GasPriceOracle contract, method getL1Fee."""
        data = SEL_GET_L1_FEE + abi_encode(["bytes"], [raw_tx])
        return int.from_bytes(self._eth_call(GAS_PRICE_ORACLE, data)[:32], "big")

    def send_raw(self, raw: bytes) -> str:
        return "0x" + bytes(self._call(self.w3.eth.send_raw_transaction, raw)).hex()

    def receipt(self, tx_hash: str) -> dict | None:
        """The transaction receipt, or None if it is not in a block yet."""
        try:
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            return None
        except Exception as exc:  # noqa: BLE001
            raise classify(exc) from exc
        return {
            "status": int(receipt["status"]),
            "block": int(receipt["blockNumber"]),
            "logs": [
                {
                    "address": log["address"],
                    "topics": [bytes(topic) for topic in log["topics"]],
                    "data": bytes(log["data"]),
                }
                for log in receipt["logs"]
            ],
        }


def find_transfer(receipt: dict, token: str, sender: str, recipient: str) -> int | None:
    """The amount from the token's Transfer event from the sender to the recipient; None — no such event."""
    source, target = bytes.fromhex(sender[2:]), bytes.fromhex(recipient[2:])
    for log in receipt["logs"]:
        topics = log["topics"]
        if (log["address"].lower() == token.lower() and len(topics) == 3 and topics[0] == TRANSFER_TOPIC
                and topics[1][-20:] == source and topics[2][-20:] == target):
            return int.from_bytes(log["data"][:32], "big")
    return None
