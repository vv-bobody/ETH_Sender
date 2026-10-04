"""wallets.txt: parsing and checking wallets (spec 3.1, 11.3)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from eth_account import Account

from app.addresses import address_error, checksum
from app.i18n import Text, t, tr
from app.text import short_address

TEMPLATE = """\
# Wallets to send from: one line per wallet.
# Format: name,private key,recipient address
# Without a name: private key,recipient address (or with a leading comma: ,private key,recipient address).
# A wallet without a name is shown by the shortened sender address.
# Formats can be mixed in one file. The key is 64 hex characters, with or without 0x.
# Empty lines and lines starting with # are skipped.
#
# Examples:
# Main 1,0x<64 hex characters>,0x1111111111111111111111111111111111111111
# 0x<64 hex characters>,0x2222222222222222222222222222222222222222
"""

_KEY = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")


@dataclass
class WalletEntry:
    num: int  # the number in the program: lines with wallets in file order, from 1
    line_no: int  # the line number in the file — for error messages
    name: str
    sender: str | None
    recipient: str | None
    error: Text | None = None
    private_key: str = field(default="", repr=False)  # never shown and never written to the log

    @property
    def valid(self) -> bool:
        return self.error is None

    @property
    def title(self) -> str | Text:
        """How the wallet is called in the log: its name, or the shortened sender address without one."""
        if self.name:
            return self.name
        return short_address(self.sender) if self.sender else t("no name")


def parse_line(num: int, line_no: int, line: str) -> WalletEntry:
    """Three fields are name,key,address; two fields are key,address — a wallet without a name (spec 11.3)."""
    parts = [part.strip() for part in line.split(",")]
    if len(parts) == 2:
        parts.insert(0, "")
    if len(parts) != 3:
        return WalletEntry(num, line_no, "", None, None,
                           error=t("expected 2 or 3 comma-separated fields: key,address or name,key,address"))
    name, key, recipient = parts
    entry = WalletEntry(num, line_no, name, None, recipient or None)
    if not _KEY.match(key):
        entry.error = t("invalid private key")
        return entry
    key = "0x" + key[-64:].lower()
    try:
        entry.sender = Account.from_key(key).address
    except Exception:  # noqa: BLE001 — the exception text is not shown: it might contain the key
        entry.error = t("invalid private key")
        return entry
    problem = address_error(recipient)
    if problem:
        entry.error = t("recipient address: {problem}", problem=problem)
        return entry
    entry.recipient = checksum(recipient)
    if entry.recipient == entry.sender:
        entry.error = t("the recipient is the same as the sender")
        return entry
    entry.private_key = key
    return entry


def parse(text: str) -> list[WalletEntry]:
    entries: list[WalletEntry] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.replace("﻿", "").strip()  # a BOM in the middle, if the file was glued from several
        if not line or line.startswith("#"):
            continue
        entries.append(parse_line(len(entries) + 1, line_no, line))
    return entries


def load(path: Path) -> tuple[list[WalletEntry], Text | None]:
    """Wallets from the file and a message for the log, if the file had to be created or could not be read."""
    if not path.exists():
        path.write_text(tr(TEMPLATE), encoding="utf-8")  # the template — in the current language (spec 12.2)
        return [], t("{file} not found: created a file with an example. Add wallets to it and click Apply.",
                     file=path.name)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        return [], t("{file} could not be read: {error}. Save the file in UTF-8 encoding.", file=path.name,
                     error=str(exc))
    return parse(text), None
