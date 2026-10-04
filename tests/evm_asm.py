"""A tiny EVM assembler and a minimal ERC-20 for the tests on a local blockchain.

The token: balanceOf, transfer (with the Transfer event, a refusal when the balance is short), decimals = 6,
symbol = "TST". On deployment the whole supply goes to the deployer.
"""
from __future__ import annotations

from app.chain import TRANSFER_TOPIC

OPCODES = {
    "STOP": 0x00, "ADD": 0x01, "SUB": 0x03, "GT": 0x11, "EQ": 0x14, "SHR": 0x1C, "SHA3": 0x20,
    "CALLER": 0x33, "CALLDATALOAD": 0x35, "CODECOPY": 0x39, "MSTORE": 0x52, "SLOAD": 0x54, "SSTORE": 0x55,
    "JUMPI": 0x57, "JUMPDEST": 0x5B, "DUP1": 0x80, "DUP2": 0x81, "DUP3": 0x82, "DUP4": 0x83, "SWAP1": 0x90,
    "LOG3": 0xA3, "RETURN": 0xF3, "REVERT": 0xFD,
}


def push(value: int, size: int) -> tuple:
    return ("push", value, size)


def assemble(program: list) -> bytes:
    """Items: an opcode name, push(value, size), ("label", name), ("jump_to", name) — PUSH2 of the label address."""
    labels, offset = {}, 0
    for item in program:
        if isinstance(item, str):
            offset += 1
        elif item[0] == "push":
            offset += 1 + item[2]
        elif item[0] == "label":
            labels[item[1]] = offset
        elif item[0] == "jump_to":
            offset += 3
    code = bytearray()
    for item in program:
        if isinstance(item, str):
            code.append(OPCODES[item])
        elif item[0] == "push":
            code.append(0x5F + item[2])
            code += item[1].to_bytes(item[2], "big")
        elif item[0] == "jump_to":
            code.append(0x61)
            code += labels[item[1]].to_bytes(2, "big")
    return bytes(code)


def _slot_of(address_ops: list) -> list:
    """keccak(address . 0) — the balance slot in mapping(address => uint256) number 0."""
    return [*address_ops, push(0, 1), "MSTORE", push(0, 1), push(0x20, 1), "MSTORE",
            push(0x40, 1), push(0, 1), "SHA3"]


def _return_word(value_ops: list) -> list:
    return [*value_ops, push(0, 1), "MSTORE", push(0x20, 1), push(0, 1), "RETURN"]


RUNTIME = assemble([
    push(0, 1), "CALLDATALOAD", push(0xE0, 1), "SHR",
    "DUP1", push(0x70A08231, 4), "EQ", ("jump_to", "balance_of"), "JUMPI",
    "DUP1", push(0xA9059CBB, 4), "EQ", ("jump_to", "transfer"), "JUMPI",
    "DUP1", push(0x313CE567, 4), "EQ", ("jump_to", "decimals"), "JUMPI",
    "DUP1", push(0x95D89B41, 4), "EQ", ("jump_to", "symbol"), "JUMPI",
    push(0, 1), "DUP1", "REVERT",

    ("label", "balance_of"), "JUMPDEST",
    *_slot_of([push(4, 1), "CALLDATALOAD"]), "SLOAD",
    *_return_word([]),

    ("label", "decimals"), "JUMPDEST",
    *_return_word([push(6, 1)]),

    ("label", "symbol"), "JUMPDEST",
    push(0x20, 1), push(0, 1), "MSTORE",
    push(3, 1), push(0x20, 1), "MSTORE",
    push(int.from_bytes(b"TST".ljust(32, b"\0"), "big"), 32), push(0x40, 1), "MSTORE",
    push(0x60, 1), push(0, 1), "RETURN",

    ("label", "transfer"), "JUMPDEST",                  # [sel]
    *_slot_of(["CALLER"]),                              # [sel, from_slot]
    "DUP1", "SLOAD",                                    # [.., from_slot, from_bal]
    push(0x24, 1), "CALLDATALOAD",                      # [.., from_bal, amount]
    "DUP2", "DUP2", "GT", ("jump_to", "fail"), "JUMPI",  # amount > from_bal → refusal
    "DUP1", "DUP3", "SUB", "DUP4", "SSTORE",            # balance[from] = from_bal - amount
    push(4, 1), "CALLDATALOAD",                         # [.., amount, to]
    "DUP1", push(0, 1), "MSTORE",                       # mem[0] = to
    push(0, 1), push(0x20, 1), "MSTORE",
    push(0x40, 1), push(0, 1), "SHA3",                  # [.., amount, to, to_slot]
    "DUP1", "SLOAD", "DUP4", "ADD", "SWAP1", "SSTORE",  # balance[to] += amount
    "DUP2", push(0, 1), "MSTORE",                       # mem[0] = amount
    "DUP1", "CALLER", push(int.from_bytes(TRANSFER_TOPIC, "big"), 32), push(0x20, 1), push(0, 1), "LOG3",
    *_return_word([push(1, 1)]),                        # return true

    ("label", "fail"), "JUMPDEST",
    push(0, 1), "DUP1", "REVERT",
])


def init_code(supply: int) -> bytes:
    """Deployment code: the whole supply to the deployer, then it returns RUNTIME."""

    def build(init_length: int) -> bytes:
        return assemble([
            push(supply, 32), *_slot_of(["CALLER"]), "SSTORE",
            push(len(RUNTIME), 2), "DUP1", push(init_length, 2), push(0, 1), "CODECOPY",
            push(0, 1), "RETURN",
        ])

    length = len(build(0))
    return build(length) + RUNTIME
