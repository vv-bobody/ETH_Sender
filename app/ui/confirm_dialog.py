"""The confirmation window before the start (spec 5.9) with the balances of the checked wallets (spec 12.1) and
a warning about a bridged token (spec 13.5)."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.i18n import Text, show, tr
from app.networks import Network
from app.ui import icons, theme
from app.ui.widgets import NetworkBand, label, set_role


@dataclass
class RunSummary:
    network: Network
    token: str
    token_address: str | None  # None — the native coin
    amount: Text | str
    wallets: int
    gas_multiplier: str
    delay: Text | str
    order: Text | str
    balances: str | None = None  # the balances of the checked wallets, as the table shows them
    balances_tooltip: str | None = None  # the same with every digit
    bridged_of: str | None = None  # the token is an old bridged version of this one: USDC.e of USDC and so on


class ConfirmDialog(QDialog):
    def __init__(self, summary: RunSummary, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Dialog")
        self.setWindowTitle(tr("Confirm sending"))
        self.setModal(True)
        self.setFixedWidth(520)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        band = NetworkBand()
        band.set_color(theme.network_color(summary.network))
        outer.addWidget(band)

        body = QVBoxLayout()
        body.setContentsMargins(28, 24, 28, 24)
        body.setSpacing(0)
        outer.addLayout(body)

        body.addWidget(label(tr("Send {token} from {count:wallets}?", token=summary.token, count=summary.wallets),
                             "DialogTitle"))
        body.addSpacing(6)
        body.addWidget(label(tr("Check the details. Sent transactions cannot be reversed."), "Hint", wrap=True))
        body.addSpacing(20)

        box = QFrame()
        box.setObjectName("SummaryBox")
        grid = QGridLayout(box)
        grid.setContentsMargins(18, 16, 18, 16)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(1, 1)

        network = QHBoxLayout()
        network.setSpacing(8)
        dot = QLabel()
        dot.setPixmap(icons.dot_icon(theme.network_color(summary.network)).pixmap(10, 10))
        network.addWidget(dot)
        network.addWidget(QLabel(summary.network.title))
        network.addWidget(label(f"chain ID {summary.network.chain_id}", "Hint"))
        network.addStretch(1)

        token = QVBoxLayout()
        token.setSpacing(4)
        token.addWidget(QLabel(summary.token))
        token.addWidget(label(summary.token_address or tr("the network's native coin"),
                              "MonoValue" if summary.token_address else "Hint"))

        rows: list[tuple[str, QWidget | QHBoxLayout | QVBoxLayout]] = [
            (tr("Network"), network),
            (tr("Token"), token),
            (tr("Amount"), QLabel(show(summary.amount))),
            (tr("count\x04Wallets"), QLabel(str(summary.wallets))),  # the number of wallets, not the page title
        ]
        if summary.balances:
            balances = label(summary.balances, "", wrap=True)
            balances.setToolTip(summary.balances_tooltip or "")
            rows.append((tr("Balances"), balances))
        rows += [
            (tr("Gas"), QLabel(tr("price multiplier {value}", value=summary.gas_multiplier))),
            (tr("Delay"), QLabel(show(summary.delay))),
            (tr("Order"), QLabel(show(summary.order))),
        ]
        for i, (title, value) in enumerate(rows):
            grid.addWidget(label(title, "FieldLabel"), i, 0, Qt.AlignmentFlag.AlignTop)
            if isinstance(value, QWidget):
                grid.addWidget(value, i, 1)
            else:
                grid.addLayout(value, i, 1)
        body.addWidget(box)
        if summary.bridged_of:
            # Exchanges often credit only the native USDC and USDT, and recipients are often exchange addresses
            body.addSpacing(16)
            body.addWidget(label(tr("{token} is a bridged version of {base}. Make sure the recipient addresses accept "
                                    "exactly this one: exchanges often credit only native {base}.",
                                    token=summary.token, base=summary.bridged_of), "Warning", wrap=True))
        body.addSpacing(24)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        cancel = QPushButton(tr("Cancel"))
        start = QPushButton(tr("Start sending"))
        set_role(start, "primary")
        for button in (cancel, start):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(38)
        cancel.clicked.connect(self.reject)
        start.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(start)
        body.addLayout(buttons)
