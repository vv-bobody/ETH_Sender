"""EVM address checks: format and the EIP-55 checksum."""
from __future__ import annotations

import re

from eth_utils import is_checksum_address, to_checksum_address

from app.i18n import Text, t

_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


def address_error(text: str) -> Text | None:
    """What is wrong with the address, or None. A mixed-case address has its checksum verified: it catches typos."""
    if not _ADDRESS.match(text):
        return t("expected an address like 0x followed by 40 characters 0–9, a–f")
    body = text[2:]
    if body not in (body.lower(), body.upper()) and not is_checksum_address(text):
        return t("the address checksum does not match, check it for a typo")
    return None


def checksum(address: str) -> str:
    return to_checksum_address(address)
