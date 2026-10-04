"""The log at the bottom of the window (spec 5.11): lines with the time, transaction hashes are explorer links.

The lines are kept, so after a language or theme switch the whole log is shown again (spec 12.2, 12.3)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from html import escape

from PySide6.QtGui import QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import QTextBrowser, QWidget

from app.i18n import Text
from app.networks import Network
from app.text import short_hash
from app.ui import theme

_TX_HASH = re.compile(r"0x[0-9a-fA-F]{64}")

LEVEL_COLOR = {"info": "TEXT", "ok": "OK", "warn": "WARN", "error": "ERROR", "muted": "MUTED"}  # palette names


@dataclass(frozen=True)
class Entry:
    when: datetime
    message: Text | str
    level: str
    network: Network | None  # which explorer the transaction links lead to


def link(url: str, text: str) -> str:
    return f'<a href="{escape(url)}">{escape(text)}</a>'


def to_html(text: str, network: Network | None) -> str:
    """Escapes the text and turns full transaction hashes into short explorer links."""
    parts, last = [], 0
    for match in _TX_HASH.finditer(text):
        tx_hash = match.group(0)
        parts.append(escape(text[last:match.start()]))
        parts.append(link(network.tx_url(tx_hash), short_hash(tx_hash)) if network else escape(short_hash(tx_hash)))
        last = match.end()
    parts.append(escape(text[last:]))
    return "".join(parts)


class LogView(QTextBrowser):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Log")
        self.setOpenExternalLinks(True)
        self.setFont(theme.mono_font())
        self.document().setDocumentMargin(4)
        self.network: Network | None = None  # links of new lines lead to this network's explorer
        self.entries: list[Entry] = []
        self._style_links()

    def add(self, message: Text | str, level: str = "info", when: datetime | None = None) -> None:
        """A log line. Text is rendered in the current language now and again after every switch."""
        entry = Entry(when or datetime.now(), message, level, self.network)
        self.entries.append(entry)
        self._append(entry)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def rerender(self) -> None:
        """Shows the whole log again: in the current language and theme."""
        bar = self.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 4
        position = bar.value()
        self.clear()
        self._style_links()
        for entry in self.entries:
            self._append(entry)
        bar.setValue(bar.maximum() if at_bottom else position)

    def _style_links(self) -> None:
        self.document().setDefaultStyleSheet(f"a {{ color: {theme.TEXT}; }}")

    def _append(self, entry: Entry) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if not self.document().isEmpty():
            cursor.insertBlock()
        color = getattr(theme, LEVEL_COLOR[entry.level])
        cursor.insertHtml(
            f'<span style="color:{theme.FAINT}">{entry.when:%H:%M:%S}</span>&nbsp;&nbsp;'
            f'<span style="color:{color}">{to_html(str(entry.message), entry.network)}</span>'
        )
        # insertHtml resets the paragraph format, so the line height is set after the insertion
        block = QTextBlockFormat()
        block.setLineHeight(150, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        cursor.setBlockFormat(block)
