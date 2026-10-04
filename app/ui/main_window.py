"""The main window (spec 4): settings on the left, wallets and the log on the right."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QMainWindow, QPushButton, QSplitter, QVBoxLayout, QWidget

from app.i18n import Text, show, tr
from app.networks import NETWORKS
from app.settings import NATIVE
from app.text import short_address
from app.totals import State as TotalState
from app.totals import Total
from app.ui import icons, theme
from app.ui.log_view import LogView
from app.ui.settings_panel import SettingsPanel
from app.ui.wallet_table import NATIVE_DECIMALS, TOKEN_DECIMALS, Col, WalletModel, WalletTable, format_amount
from app.ui.widgets import ElidedLabel, NetworkBand, Pill, label, set_role
from app.units import plain


def sum_parts(totals: Total, token: Text | str, native: str | None) -> list[tuple[str, str]]:
    """Each sum as the table shows it and with every digit (spec 12.1): [("342.80 USDC", "342.8 USDC"), …].
    native None — the native coin itself is sent, there is one sum."""
    token = show(token)
    parts = [(f"{format_amount(totals.token, *TOKEN_DECIMALS)} {token}", f"{plain(totals.token)} {token}")]
    if native is not None:
        parts.append((f"{format_amount(totals.native, *NATIVE_DECIMALS)} {native}", f"{plain(totals.native)} {native}"))
    return parts


def sums_text(totals: Total, token: Text | str, native: str | None) -> tuple[str, str]:
    """Sums for a label and with every digit for its tooltip: "342.80 USDC · 0.0150 ETH"."""
    parts = sum_parts(totals, token, native)
    return " · ".join(short for short, _ in parts), " · ".join(full for _, full in parts)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ETH Sender")
        self.setWindowIcon(icons.app_icon())
        self.resize(1600, 940)
        self.setMinimumSize(1180, 720)
        self.close_guard: Callable[[], bool] | None = None  # ask before closing during the mailing
        self._file_summary: tuple[int, int] | None = None
        self._token: tuple[Text | str, str | None] = ("", None)
        self._run_status: Text | None = None
        self.retry_allowed = False  # the balances may be polled again: applied, no polling, no mailing

        central = QFrame()
        central.setObjectName("Central")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.settings = SettingsPanel()
        root.addWidget(self.settings)

        main = QFrame()
        main.setObjectName("Main")
        column = QVBoxLayout(main)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.band = NetworkBand()
        column.addWidget(self.band)
        content = QVBoxLayout()
        content.setContentsMargins(28, 22, 28, 22)
        content.setSpacing(0)
        column.addLayout(content, 1)
        root.addWidget(main, 1)

        content.addLayout(self._build_header())
        content.addSpacing(18)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(16)
        splitter.addWidget(self._build_wallets())
        splitter.addWidget(self._build_log())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([600, 240])
        content.addWidget(splitter, 1)

        self.setCentralWidget(central)

        self.model.checked_changed.connect(self.update_counter)
        self.model.balances_changed.connect(self.update_counter)
        self.model.balances_changed.connect(self.update_retry_button)
        self.settings.network_changed.connect(self._on_network)
        self.settings.token_changed.connect(self._on_token)
        self._on_network(self.settings.current_network().key)
        self.retranslate()

    # --- building --------------------------------------------------------------------------------------

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title = label("", "PageTitle")
        titles.addWidget(self.title)
        self.counter = label("", "Counter")
        titles.addWidget(self.counter)
        header.addLayout(titles)
        header.addStretch(1)
        self.network_pill = Pill()
        self.token_pill = Pill()
        header.addWidget(self.network_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.token_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        return header

    def _build_wallets(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        self.model = WalletModel()
        self.table = WalletTable(self.model)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.select_all = QPushButton()
        self.select_none = QPushButton()
        self.checked_label = ElidedLabel(name="Counter")
        self.retry_button = QPushButton()
        self.retry_button.setIconSize(QSize(14, 14))
        self.run_status = label("", "RunStatus")
        self.stop_button = QPushButton()
        self.start_button = QPushButton()
        set_role(self.stop_button, "danger")
        set_role(self.start_button, "primary")
        self.stop_button.setMinimumWidth(96)
        self.start_button.setMinimumWidth(128)
        for button in (self.select_all, self.select_none, self.retry_button, self.stop_button, self.start_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(38)
        actions.addWidget(self.select_all)
        actions.addWidget(self.select_none)
        actions.addSpacing(10)
        actions.addWidget(self.checked_label)
        actions.addSpacing(6)
        actions.addWidget(self.retry_button)
        actions.addStretch(1)
        actions.addWidget(self.run_status)
        actions.addSpacing(14)
        actions.addWidget(self.stop_button)
        actions.addWidget(self.start_button)
        layout.addLayout(actions)

        self.select_all.clicked.connect(lambda: self.model.set_all(True))
        self.select_none.clicked.connect(lambda: self.model.set_all(False))
        self.stop_button.setEnabled(False)
        self.retry_button.hide()
        return box

    def _build_log(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("LogFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 12, 8, 8)
        layout.setSpacing(6)
        self.log_title = label("", "PanelTitle")
        layout.addWidget(self.log_title)
        self.log = LogView()
        layout.addWidget(self.log, 1)
        return frame

    # --- language and theme ----------------------------------------------------------------------------

    def retranslate(self) -> None:
        """Every text of the window in the current language, the log and the statuses included (spec 12.2)."""
        self.settings.retranslate()
        self.title.setText(tr("Wallets"))
        self.log_title.setText(tr("Log"))
        self.select_all.setText(tr("Select all"))
        self.select_none.setText(tr("Deselect all"))
        self.stop_button.setText(tr("Stop"))
        self.start_button.setText(tr("Start"))
        self._show_file_summary()
        self._show_token()
        self.set_run_status(self._run_status)
        self.model.retranslate()
        self.update_counter()
        self.update_retry_button()
        self.log.rerender()

    def restyle(self) -> None:
        """Everything drawn in code in the current theme's colors (spec 12.3)."""
        self.settings.restyle()
        self._on_network(self.settings.current_network().key)
        self.table.retheme()
        self.update_retry_button()
        self.log.rerender()
        theme.style_titlebar(self)

    # --- state -----------------------------------------------------------------------------------------

    def _on_network(self, key: str) -> None:
        network = NETWORKS[key]
        color = theme.network_color(network)
        self.band.set_color(color)
        self.network_pill.set(network.title, f"chain ID {network.chain_id}", color)
        self._on_token()

    def _on_token(self) -> None:
        """The choice in the panel: before Apply the symbol of a custom ERC-20 is not known yet."""
        key = self.settings.token_key()
        address = self.settings.token_address.text() if key != NATIVE else None
        self.show_token(self.settings.token_label(), address)

    def show_token(self, token: Text | str, address: str | None) -> None:
        """The token badge in the header and the balance column titles; address None — the native coin."""
        self._token = (token, address)
        self._show_token()

    def _show_token(self) -> None:
        token, address = self._token
        if address is None:
            self.token_pill.set(show(token), tr("native coin"))
        elif address.startswith("0x"):
            self.token_pill.set(show(token), short_address(address), mono_sub=True)
        else:
            self.token_pill.set(show(token), tr("address not set"))
        self.model.set_labels(token, self.settings.current_network().symbol)
        self.table.setColumnHidden(Col.NATIVE, address is None)
        self.update_counter()

    def update_counter(self) -> None:
        """"9 of 11 selected" and the balances of the checked wallets (spec 12.1)."""
        checked, valid, _ = self.model.counts()
        text = tr("{checked} of {total} selected", checked=checked, total=valid)
        tooltip = None
        totals = self.model.totals(checked_only=True)
        if checked and totals.state is TotalState.LOADING:
            text += " · …"
        elif checked and totals.state is TotalState.READY:
            short, full = sums_text(totals, self.model.token_label, self.native_label())
            text += f" · {short}"
            tooltip = full
            if totals.failed:
                note = tr("{count:wallets} excluded: balance check failed", count=len(totals.failed))
                text += f" · {note}"
                tooltip += "\n" + note
        self.checked_label.setText(text, tooltip)

    def native_label(self) -> str | None:
        """The native coin column, if it is shown: otherwise the native coin itself is sent."""
        return None if self.table.isColumnHidden(Col.NATIVE) else self.model.native_label

    def update_retry_button(self) -> None:
        """"Retry failed (N)" is visible while some balances failed to load (spec 12.5)."""
        failed = len(self.model.failed_rows())
        self.retry_button.setVisible(failed > 0 and self.retry_allowed)
        self.retry_button.setText(tr("Retry failed ({count})", count=failed))
        self.retry_button.setIcon(icons.retry_icon(theme.TEXT))

    def set_retry_allowed(self, allowed: bool) -> None:
        self.retry_allowed = allowed
        self.model.retry_enabled = allowed
        self.table.viewport().update()
        self.update_retry_button()

    def set_run_status(self, text: Text | None) -> None:
        self._run_status = text
        self.run_status.setText(show(text))

    def set_file_summary(self, total: int, invalid: int) -> None:
        self._file_summary = (total, invalid)
        self._show_file_summary()

    def _show_file_summary(self) -> None:
        if self._file_summary is None:
            self.counter.setText("")
            return
        total, invalid = self._file_summary
        if invalid:
            self.counter.setText(tr("{count:entries} in wallets.txt, {invalid} with an error", count=total,
                                    invalid=invalid))
        else:
            self.counter.setText(tr("{count:entries} in wallets.txt", count=total))

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.close_guard is not None and not self.close_guard():
            event.ignore()
            return
        event.accept()

    def set_running(self, running: bool) -> None:
        """During the mailing the settings, the checkboxes and Start are locked (spec 5.9)."""
        self.settings.set_locked(running)
        self.model.locked = running
        self.table.viewport().update()
        for button in (self.select_all, self.select_none, self.start_button):
            button.setEnabled(not running)
        self.stop_button.setEnabled(running)
