"""Real sending on a local blockchain (eth-tester + py-evm): web3, signing, receipts, the Transfer event.

Needed only for development: pip install eth-tester "py-evm==0.12.1b1". Without it the tests are skipped.
"""
from __future__ import annotations

import random
import warnings
from decimal import Decimal

import pytest

eth_tester = pytest.importorskip("eth_tester")
warnings.filterwarnings("ignore")

from eth_account import Account  # noqa: E402
from web3 import EthereumTesterProvider, Web3  # noqa: E402

from app.apply import resolve_token  # noqa: E402
from app.chain import Chain, ChainError, transfer_data  # noqa: E402
from app.networks import Network  # noqa: E402
from app.sender import Outcome, Plan, Token, WalletSender  # noqa: E402
from app.units import human  # noqa: E402
from app.wallets import WalletEntry  # noqa: E402
from tests.evm_asm import init_code  # noqa: E402

KEY = "0x" + "42" * 32
RECIPIENT = "0x2222222222222222222222222222222222222222"


class Recorder:
    def __init__(self) -> None:
        self.logs: list[str] = []

    def progress(self, status, marks, tx_hash) -> None:
        pass

    def log(self, text, level: str = "info") -> None:
        self.logs.append(str(text))


@pytest.fixture()
def local():
    w3 = Web3(EthereumTesterProvider())
    network = Network(key="local", title="Local", chain_id=w3.eth.chain_id, symbol="ETH", eip1559=True,
                      l1_fee=False, explorer="http://localhost", default_rpc="", color="#ffffff",
                      light_color="#000000", tokens=())
    chain = Chain(network, "", w3=w3)
    funder = w3.eth.accounts[0]
    sender = Account.from_key(KEY).address
    w3.eth.wait_for_transaction_receipt(w3.eth.send_transaction({"from": funder, "to": sender, "value": 10**18}))
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.send_transaction({"from": funder, "data": init_code(10**15), "gas": 1_000_000}))
    token = receipt["contractAddress"]
    w3.eth.wait_for_transaction_receipt(w3.eth.send_transaction(
        {"from": funder, "to": token, "data": transfer_data(sender, 250_000_000), "gas": 200_000}))
    return w3, network, chain, token


def plan(mode: str = "all", **kwargs) -> Plan:
    return Plan(mode, Decimal(kwargs.get("percent", "100")), kwargs.get("rmin"), kwargs.get("rmax"),
                Decimal("1.2"), 30)


def wallet() -> WalletEntry:
    return WalletEntry(1, 1, "Test", Account.from_key(KEY).address, RECIPIENT, private_key=KEY)


def test_native_all_really_arrives_and_only_dust_is_left(local):
    w3, network, chain, _ = local
    before = w3.eth.get_balance(wallet().sender)
    result = WalletSender(chain, network, Token(None, 18, "ETH"), plan(), wallet(), Recorder(),
                          rng=random.Random(1)).run()
    assert result.outcome is Outcome.OK, result.detail
    received = w3.eth.get_balance(RECIPIENT)
    left = w3.eth.get_balance(wallet().sender)
    assert received > 0 and left >= 0
    assert before - received - left < 10**15  # only gas was spent
    assert w3.eth.get_transaction(result.tx_hash)["value"] == received


def test_token_range_transfer_is_checked_by_transfer_event(local):
    w3, network, chain, token_address = local
    token = resolve_token(chain, network, token_address)
    assert token.label == "TST" and token.decimals == 6
    assert chain.token_balance(token_address, wallet().sender) == 250_000_000
    result = WalletSender(chain, network, token, plan("range", rmin=Decimal(10), rmax=Decimal(15)), wallet(),
                          Recorder(), rng=random.Random(5)).run()
    assert result.outcome is Outcome.OK, result.detail
    received = chain.token_balance(token_address, RECIPIENT)
    assert 10_000_000 <= received <= 15_000_000 and received % 100 == 0
    assert str(result.status) == f"Success: {human(received, 6)} TST"
    receipt = chain.receipt(result.tx_hash)
    assert receipt["status"] == 1 and len(receipt["logs"]) == 1


def test_token_all_moves_whole_balance(local):
    w3, network, chain, token_address = local
    token = resolve_token(chain, network, token_address)
    result = WalletSender(chain, network, token, plan(), wallet(), Recorder()).run()
    assert result.outcome is Outcome.OK
    assert chain.token_balance(token_address, wallet().sender) == 0
    assert chain.token_balance(token_address, RECIPIENT) == 250_000_000


def test_transfer_over_balance_is_rejected_by_contract_at_estimate(local):
    _, _, chain, token_address = local
    with pytest.raises(ChainError) as error:
        chain.estimate_gas(wallet().sender, token_address, 0, transfer_data(RECIPIENT, 10**12))
    assert error.value.kind == ChainError.REVERTED
