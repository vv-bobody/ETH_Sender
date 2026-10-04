"""How node answers become ChainError: it decides whether to retry (spec 5.6, 12.5); reading blocks (spec 13.4)."""
from __future__ import annotations

from decimal import Decimal

import pytest
import requests
from web3 import Web3
from web3.exceptions import Web3RPCError
from web3.providers.base import BaseProvider

from app.chain import TRANSFER_TOPIC, Chain, ChainError, classify, find_transfer, transfer_data
from app.networks import NETWORKS


@pytest.mark.parametrize(("message", "kind"), [
    ("{'code': -32000, 'message': 'insufficient funds for gas * price + value'}", ChainError.INSUFFICIENT_FUNDS),
    ("Sender does not have enough balance to cover transaction value and gas", ChainError.INSUFFICIENT_FUNDS),
    ("{'code': -32010, 'message': 'insufficient sender balance'}", ChainError.INSUFFICIENT_FUNDS),
    ("{'code': -32000, 'message': 'nonce too low: next nonce 5, tx nonce 4'}", ChainError.NONCE_TOO_LOW),
    ("{'code': -32000, 'message': 'replacement transaction underpriced'}", ChainError.UNDERPRICED),
    ("{'code': -32000, 'message': 'max fee per gas less than block base fee'}", ChainError.UNDERPRICED),
    ("{'code': -32000, 'message': 'already known'}", ChainError.ALREADY_KNOWN),
    ("{'code': 3, 'message': 'execution reverted: ERC20: transfer amount exceeds balance'}", ChainError.REVERTED),
    ("{'code': 3, 'message': 'execution reverted: insufficient funds'}", ChainError.REVERTED),
    ("{'code': -32003, 'message': 'EVM error: InvalidFEOpcode'}", ChainError.REVERTED),  # USDT in Ethereum, Reth
    ("{'code': -32000, 'message': 'invalid opcode: INVALID'}", ChainError.REVERTED),  # the same in Geth
    ("{'code': -32000, 'message': 'header not found'}", ChainError.RPC),
])
def test_node_messages(message, kind):
    error = classify(Exception(message))
    assert error.kind == kind and not error.rate_limited


def test_unknown_node_error_means_rejected_not_lost():
    assert classify(Web3RPCError("{'code': -32000, 'message': 'intrinsic gas too low'}")).kind == ChainError.REJECTED


def test_network_failures_are_retryable():
    assert classify(requests.exceptions.ConnectTimeout()).kind == ChainError.RPC
    assert classify(requests.exceptions.ConnectionError()).kind == ChainError.RPC
    response = requests.Response()
    response.status_code = 503
    error = classify(requests.exceptions.HTTPError(response=response))
    assert error.kind == ChainError.RPC and "503" in str(error) and not error.rate_limited


@pytest.mark.parametrize("message", [
    "{'code': -32016, 'message': 'over rate limit'}",  # public OP Stack RPCs: Base, Optimism
    "{'code': -32005, 'message': 'project ID request rate exceeded'}",  # Infura
    "{'code': 429, 'message': 'Your app has exceeded its compute units per second capacity'}",  # Alchemy
    "{'code': -32000, 'message': 'Too Many Requests'}",
])
def test_rate_limit_answers_of_nodes(message):
    """A rate limit is an RPC error to retry later — not a refusal of the node (spec 12.5)."""
    for exc in (Web3RPCError(message), Exception(message)):
        error = classify(exc)
        assert error.kind == ChainError.RPC and error.rate_limited


def test_rate_limit_code_is_read_from_the_rpc_response():
    exc = Web3RPCError("rejected", rpc_response={"jsonrpc": "2.0", "id": 1,
                                                 "error": {"code": -32016, "message": "slow down"}})
    assert classify(exc).rate_limited


def test_http_429_is_a_rate_limit():
    response = requests.Response()
    response.status_code = 429
    error = classify(requests.exceptions.HTTPError(response=response))
    assert error.kind == ChainError.RPC and error.rate_limited and "429" in str(error)


def test_transfer_event_is_matched_by_token_sender_and_recipient():
    sender = "0x1111111111111111111111111111111111111111"
    recipient = "0x2222222222222222222222222222222222222222"
    token = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    log = {"address": token.lower(), "data": (5).to_bytes(32, "big"),
           "topics": [TRANSFER_TOPIC, bytes(12) + bytes.fromhex(sender[2:]), bytes(12) + bytes.fromhex(recipient[2:])]}
    assert find_transfer({"logs": [log]}, token, sender, recipient) == 5
    assert find_transfer({"logs": [log]}, token, recipient, sender) is None
    assert find_transfer({"logs": [{**log, "address": sender}]}, token, sender, recipient) is None
    assert transfer_data(recipient, 5)[:4].hex() == "a9059cbb"


class BlockNode(BaseProvider):
    """A node whose latest block has extraData longer than 32 bytes, as some Avalanche blocks do (spec 13.4)."""

    def __init__(self, extra_data_bytes: int) -> None:
        super().__init__()
        self.extra = "0x" + "00" * extra_data_bytes

    def make_request(self, method, params):
        results = {
            "eth_getBlockByNumber": {"number": "0x5c0e0fa", "hash": "0x" + "11" * 32, "parentHash": "0x" + "22" * 32,
                                     "extraData": self.extra, "baseFeePerGas": hex(5_030_191_349),
                                     "transactions": [], "timestamp": "0x1"},
            "eth_maxPriorityFeePerGas": "0x1",
            "eth_feeHistory": {"oldestBlock": "0x5c0e0f1", "baseFeePerGas": [hex(5 * 10**9)] * 11,
                               "gasUsedRatio": [0.5] * 10, "reward": [["0x1"]] * 9 + [[hex(150)]]},
        }
        return {"jsonrpc": "2.0", "id": 1, "result": results[method]}


@pytest.mark.parametrize("extra_data_bytes", [6, 32, 66])
def test_avalanche_blocks_with_long_extra_data_are_read(extra_data_bytes):
    chain = Chain(NETWORKS["avalanche"], "", w3=Web3(BlockNode(extra_data_bytes)))
    fees = chain.fees(Decimal("1.2"))
    assert not fees.legacy and fees.priority_fee == 2  # the median tip of 1 wei × 1.2, rounded up
    assert fees.max_fee == -(-(5_030_191_349 + 1) * 12 // 10)
