"""A read-only check of every network's RPC: nothing is sent.

Run from the project root: .venv\\Scripts\\python tools\\check_networks.py
Checks the chain ID, the ready-made tokens (symbol, decimals), the gas price, gas estimation, the L1 fee,
the nonce and a receipt request. The signing key is created at random and is never saved.
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from eth_account import Account  # noqa: E402

from app.chain import Chain, ChainError, transfer_data  # noqa: E402
from app.networks import NETWORKS  # noqa: E402
from app.units import gwei, human  # noqa: E402


def check(network_key: str) -> bool:
    network = NETWORKS[network_key]
    chain = Chain(network, network.default_rpc)
    probe = Account.create()  # an empty random wallet: only for gas estimation and signing
    ok = True

    def line(text: str, good: bool = True) -> None:
        nonlocal ok
        ok &= good
        print(f"  {'OK ' if good else 'ERR'} {text}")

    print(f"{network.title} ({network.default_rpc})")
    try:
        chain_id = chain.chain_id()
        line(f"chain ID {chain_id}", chain_id == network.chain_id)
        for preset in network.tokens:
            symbol, decimals = chain.token_info(preset.address)
            has_code = chain.has_code(preset.address)
            line(f"{preset.label}: contract {'present' if has_code else 'MISSING'}, symbol {symbol}, "
                 f"decimals {decimals}", has_code and decimals == preset.decimals)
        fees = chain.fees(Decimal("1.2"))
        line(f"gas price ×1.2: max {gwei(fees.max_fee)} gwei, tip {gwei(fees.priority_fee)} gwei, "
             f"{'legacy' if fees.legacy else 'EIP-1559'}", fees.legacy == (not network.eip1559))
        gas = chain.estimate_gas(probe.address, probe.address, 0, b"")
        line(f"gas estimate of a {network.symbol} transfer: {gas}", gas >= 21000)
        if network.tokens:
            token = network.tokens[0]
            try:
                chain.estimate_gas(probe.address, token.address, 0, transfer_data(probe.address, 1))
                line(f"estimating a {token.label} transfer from an empty wallet succeeded (expected a refusal)", False)
            except ChainError as exc:
                line(f"a {token.label} transfer from an empty wallet is rejected at estimation: {exc.kind}",
                     exc.kind == ChainError.REVERTED)
        latest, pending = chain.nonces(probe.address)
        line(f"nonce of the empty wallet: {latest}/{pending}", latest == pending == 0)
        line(f"balance of the empty wallet: {human(chain.native_balance(probe.address), 18)} {network.symbol}")
        if network.l1_fee:
            tx = {"chainId": network.chain_id, "nonce": 0, "to": probe.address, "value": 10**15, "data": b"",
                  "gas": gas, **fees.tx_fields()}
            raw = bytes(Account.sign_transaction(tx, probe.key).raw_transaction)
            l1 = chain.l1_fee(raw)
            line(f"L1 fee of a transfer: {human(l1, 18)} ETH", l1 > 0)
        line(f"receipt of a missing transaction: {chain.receipt('0x' + '00' * 32)}")
    except ChainError as exc:
        line(f"RPC error ({exc.kind}{', rate limit' if exc.rate_limited else ''}): {exc}", False)
    return ok


def main() -> int:
    results = {key: check(key) for key in NETWORKS}
    print()
    print("Summary:", ", ".join(f"{NETWORKS[key].title} {'OK' if good else 'ERROR'}" for key, good in results.items()))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
