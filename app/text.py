"""Short forms of addresses and transaction hashes for the table and the log."""
from __future__ import annotations


def short_address(address: str) -> str:
    return f"{address[:6]}…{address[-4:]}"


def short_hash(tx_hash: str) -> str:
    return f"{tx_hash[:6]}…{tx_hash[-4:]}"
