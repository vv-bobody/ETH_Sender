"""The settings panel on the left (spec 4.3) with the language and theme switches in its header (spec 12.2, 12.3)."""
from __future__ import annotations

from decimal import Decimal
from urllib.parse import urlparse

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from app.i18n import RU, Text, show, tr
from app.networks import NETWORKS, Network
from app.settings import NATIVE, Settings
from app.ui import icons, theme
from app.ui.widgets import COMPACT_HEIGHT, Collapsible, Combo, DecimalSpin, IntSpin, Segmented, label, set_role

CUSTOM = "custom"


class SettingsPanel(QFrame):
    apply_requested = Signal()
    network_changed = Signal(str)
    token_changed = Signal()
    edited = Signal()  # the user changed one of the settings
    language_requested = Signal(str)  # the RU | EN switch: only the view, not a setting of the mailing
    theme_requested = Signal()  # the theme icon was clicked

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(340)
        self._loading = False
        self._custom_address = ""
        self._last_token = NATIVE
        self._attention: Text | None = None
        self._token_info: Text | None = None
        self._labels: list[tuple[QLabel, str]] = []  # labels to translate again on a language switch

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        # The header with the switches is outside the scrolled and locked part: they work at any moment
        outer.addWidget(self._build_head())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body_widget = QWidget()
        self._body_widget.setObjectName("SidebarBody")
        self._body_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._body = QVBoxLayout(self._body_widget)
        self._body.setContentsMargins(24, 6, 22, 24)
        self._body.setSpacing(0)
        scroll.setWidget(self._body_widget)
        outer.addWidget(scroll, 1)

        self._build_network()
        self._build_amount()
        self._build_timing()
        self._build_rpc()
        self._body.addStretch(1)
        outer.addWidget(self._build_footer())

        self.network.currentIndexChanged.connect(self._on_network)
        self.token.currentIndexChanged.connect(self._on_token)
        self.token_address.textChanged.connect(lambda: self.token_key() == CUSTOM and self.token_changed.emit())
        self.amount_mode.changed.connect(self._on_amount_mode)
        for signal in (
            self.network.currentIndexChanged, self.token.currentIndexChanged, self.token_address.textEdited,
            self.amount_mode.changed, self.percent.valueChanged, self.range_min.valueChanged,
            self.range_max.valueChanged, self.gas_multiplier.valueChanged, self.delay_min.valueChanged,
            self.delay_max.valueChanged, self.order.changed, self.tx_timeout.valueChanged,
            *(edit.textEdited for edit in self.rpc.values()),
        ):
            signal.connect(self._on_edited)
        self.language.changed.connect(self.language_requested)
        self.theme_button.clicked.connect(self.theme_requested)
        self._on_network()
        self.retranslate()
        self.restyle()

    # --- building --------------------------------------------------------------------------------------

    def _tr_label(self, text: str, name: str, *, wrap: bool = False) -> QLabel:
        """A label whose English text is translated now and after every language switch."""
        widget = label(tr(text), name, wrap=wrap)
        self._labels.append((widget, text))
        return widget

    def _section(self, title: str, *, first: bool = False) -> None:
        if not first:
            self._body.addSpacing(30)
        self._body.addWidget(self._tr_label(title, "SectionTitle"))
        self._body.addSpacing(14)

    def _field(self, title: str, content: QWidget | QLayout, *, last: bool = False) -> None:
        self._body.addWidget(self._tr_label(title, "FieldLabel"))
        self._body.addSpacing(6)
        if isinstance(content, QWidget):
            self._body.addWidget(content)
        else:
            self._body.addLayout(content)
        if not last:
            self._body.addSpacing(16)

    @staticmethod
    def _row(*items: QWidget | int) -> QHBoxLayout:
        """A row of widgets; a number is a gap in pixels."""
        row = QHBoxLayout()
        row.setSpacing(8)
        for item in items:
            if isinstance(item, int):
                row.addSpacing(item)
            else:
                row.addWidget(item)
        row.addStretch(1)
        return row

    def _build_head(self) -> QWidget:
        """The program name and version, the RU | EN switch and the theme icon (spec 12.2, 12.3). The version goes
        under the name: next to it the line would not fit the panel width."""
        head = QWidget()
        head.setObjectName("SidebarHead")
        head.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(head)
        row.setContentsMargins(24, 22, 22, 22)
        row.setSpacing(8)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(label("ETH Sender", "Wordmark"))
        self.version = label("", "Version")
        titles.addWidget(self.version)
        row.addLayout(titles)
        row.addStretch(1)
        self.language = Segmented([(RU, "RU"), ("en", "EN")], compact=True)
        self.language.set_value("en")
        self.theme_button = QToolButton()
        self.theme_button.setObjectName("ThemeToggle")
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_button.setIconSize(QSize(16, 16))
        self.theme_button.setFixedSize(COMPACT_HEIGHT, COMPACT_HEIGHT)  # square, as high as RU | EN (spec 13.3)
        row.addWidget(self.language, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.theme_button, 0, Qt.AlignmentFlag.AlignVCenter)
        return head

    def _build_network(self) -> None:
        self._section("Network and token", first=True)
        self.network = Combo()
        self.network.setIconSize(QSize(10, 10))
        for network in NETWORKS.values():
            self.network.addItem(network.title, network.key)
        self._field("Network", self.network)

        self.token = Combo()
        self.token_address = QLineEdit()
        self.token_address.setObjectName("Mono")
        self.token_info = label("", "TokenInfo", wrap=True)
        box = QVBoxLayout()
        box.setSpacing(8)
        box.addWidget(self.token)
        box.addWidget(self.token_address)
        box.addWidget(self.token_info)
        self._field("Token", box, last=True)

    def _build_amount(self) -> None:
        self._section("Amount")
        self.amount_mode = Segmented([("all", ""), ("percent", ""), ("range", "")])
        self._body.addWidget(self.amount_mode)
        self._body.addSpacing(12)

        self.all_hint = label("", "Hint", wrap=True)

        self.percent = DecimalSpin(2, 0.01, 100)
        self.percent.setValue(100)
        self.percent.setFixedWidth(84)

        self.range_min = DecimalSpin(4, 0, 1e12)
        self.range_max = DecimalSpin(4, 0, 1e12)
        for spin in (self.range_min, self.range_max):
            spin.setFixedWidth(84)
        self.range_unit = label("", "Unit")

        self.amount_pages = QStackedWidget()
        for content in (
            self.all_hint,
            self._row(self.percent, self._tr_label("% of balance", "Unit")),
            self._row(self._tr_label("from", "Unit"), self.range_min, 4, self._tr_label("to", "Unit"), self.range_max,
                      2, self.range_unit),
        ):
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            if isinstance(content, QWidget):
                layout.addWidget(content)
            else:
                layout.addLayout(content)
            layout.addStretch(1)
            self.amount_pages.addWidget(page)
        self.amount_pages.setFixedHeight(40)
        self._body.addWidget(self.amount_pages)

    def _build_timing(self) -> None:
        self._section("Gas and delays")
        self.gas_multiplier = DecimalSpin(2, 1.0, 5.0)
        self.gas_multiplier.setPrefix("× ")
        self.gas_multiplier.setValue(1.2)
        self.gas_multiplier.setFixedWidth(84)
        self._field("Gas price multiplier", self._row(self.gas_multiplier))

        self.delay_min = IntSpin(0, 86400)
        self.delay_max = IntSpin(0, 86400)
        for spin in (self.delay_min, self.delay_max):
            spin.setFixedWidth(84)
        self.delay_min.setValue(30)
        self.delay_max.setValue(90)
        self._field("Delay between wallets", self._row(
            self._tr_label("from", "Unit"), self.delay_min, 4, self._tr_label("to", "Unit"), self.delay_max, 2,
            self._tr_label("sec", "Unit")))

        self.order = Segmented([("sequential", ""), ("random", "")])
        self._field("Processing order", self.order)

        self.tx_timeout = IntSpin(10, 3600)
        self.tx_timeout.setValue(120)
        self.tx_timeout.setFixedWidth(84)
        self._field("Confirmation timeout", self._row(self.tx_timeout, self._tr_label("sec", "Unit")), last=True)

    def _build_rpc(self) -> None:
        self._body.addSpacing(30)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.rpc: dict[str, QLineEdit] = {}
        self._rpc_dots: dict[str, QLabel] = {}
        for i, network in enumerate(NETWORKS.values()):
            if i:
                layout.addSpacing(10)
            dot = QLabel()
            head = QHBoxLayout()
            head.setSpacing(8)
            head.addWidget(dot)
            head.addWidget(label(network.title, "FieldLabel"))
            head.addStretch(1)
            edit = QLineEdit(network.default_rpc)
            edit.setPlaceholderText("https://…")
            layout.addLayout(head)
            layout.addWidget(edit)
            self.rpc[network.key] = edit
            self._rpc_dots[network.key] = dot
            edit.textChanged.connect(self._update_rpc_summary)
        self.rpc_section = Collapsible("", content)
        self._body.addWidget(self.rpc_section)

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("SidebarFooter")
        layout = QVBoxLayout(footer)
        layout.setContentsMargins(24, 14, 22, 20)
        layout.setSpacing(10)
        self.attention = label("", "DirtyHint", wrap=True)
        self.apply_button = QPushButton()
        self.apply_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_button.setMinimumHeight(40)
        self.apply_button.clicked.connect(self.apply_requested)
        layout.addWidget(self.attention)
        layout.addWidget(self.apply_button)
        return footer

    # --- language and theme ----------------------------------------------------------------------------

    def retranslate(self) -> None:
        """Every text of the panel in the current language (spec 12.2)."""
        for widget, text in self._labels:
            widget.setText(tr(text))
        self.version.setText(tr("version {version}", version=__version__))
        self.token_address.setPlaceholderText(tr("Contract address, 0x…"))
        self.amount_mode.set_texts({"all": tr("Full balance"), "percent": tr("Percent"), "range": tr("Range")})
        self.order.set_texts({"sequential": tr("File order"), "random": tr("Random")})
        self.rpc_section.set_title(tr("RPC endpoints"))
        self.apply_button.setText(tr("Apply"))
        self._fill_tokens()
        self._update_all_hint()
        self._update_rpc_summary()
        self.set_attention(self._attention)
        self.set_token_info(self._token_info)
        self._update_theme_button()

    def restyle(self) -> None:
        """Icons and dots drawn in the current theme's colors (spec 12.3)."""
        for i in range(self.network.count()):
            self.network.setItemIcon(i, icons.dot_icon(theme.network_color(NETWORKS[self.network.itemData(i)])))
        for key, dot in self._rpc_dots.items():
            dot.setPixmap(icons.dot_icon(theme.network_color(NETWORKS[key])).pixmap(10, 10))
        self.rpc_section.refresh_icon()
        self._update_theme_button()

    def _update_theme_button(self) -> None:
        dark = theme.is_dark()
        self.theme_button.setIcon(icons.moon_icon(theme.MUTED) if dark else icons.sun_icon(theme.MUTED))
        self.theme_button.setToolTip(tr("Switch to light theme") if dark else tr("Switch to dark theme"))

    def set_language(self, code: str) -> None:
        """Shows the language without asking for it again."""
        self.language.blockSignals(True)
        self.language.set_value(code)
        self.language.blockSignals(False)

    # --- values ----------------------------------------------------------------------------------------

    def current_network(self) -> Network:
        return NETWORKS[self.network.currentData()]

    def token_key(self) -> str:
        return self.token.currentData() or NATIVE

    def token_label(self) -> Text | str:
        """How the token is called before Apply: the coin symbol, the ready-made token name or just "token"."""
        network, key = self.current_network(), self.token_key()
        if key == NATIVE:
            return network.symbol
        preset = network.preset(key)
        return preset.label if preset else Text("token")

    def get_settings(self) -> Settings:
        key = self.token_key()
        range_min, range_max = self._decimal(self.range_min), self._decimal(self.range_max)
        return Settings(
            network=self.current_network().key,
            token=self.token_address.text().strip() if key == CUSTOM else key,
            amount_mode=self.amount_mode.value(),
            percent=self._decimal(self.percent),
            range_min=range_min or None,  # 0 in the field means "not set"
            range_max=range_max or None,
            gas_multiplier=self._decimal(self.gas_multiplier),
            delay_min=self.delay_min.value(),
            delay_max=self.delay_max.value(),
            order=self.order.value(),
            tx_timeout=self.tx_timeout.value(),
            rpc={key: edit.text().strip() for key, edit in self.rpc.items()},
            language=self.language.value(),
            theme="dark" if theme.is_dark() else "light",
        )

    def set_settings(self, settings: Settings) -> None:
        self._loading = True
        try:
            index = self.network.findData(settings.network)
            self.network.setCurrentIndex(index if index >= 0 else 0)
            if settings.custom_token:
                self._custom_address = settings.token
                self.token.setCurrentIndex(self.token.findData(CUSTOM))
            else:
                index = self.token.findData(settings.token)
                self.token.setCurrentIndex(index if index >= 0 else 0)  # the network has no such token — native
            self._on_token()
            self.amount_mode.set_value(settings.amount_mode)
            self.percent.setValue(float(settings.percent))
            self.range_min.setValue(float(settings.range_min or 0))
            self.range_max.setValue(float(settings.range_max or 0))
            self.gas_multiplier.setValue(float(settings.gas_multiplier))
            self.delay_min.setValue(settings.delay_min)
            self.delay_max.setValue(settings.delay_max)
            self.order.set_value(settings.order)
            self.tx_timeout.setValue(settings.tx_timeout)
            for key, edit in self.rpc.items():
                edit.setText(settings.rpc.get(key, ""))
        finally:
            self._loading = False

    @staticmethod
    def _decimal(spin: DecimalSpin) -> Decimal:
        return Decimal(spin.textFromValue(spin.value()))

    # --- reactions to choices --------------------------------------------------------------------------

    def _on_edited(self, *_) -> None:
        if not self._loading:
            self.edited.emit()

    def _fill_tokens(self) -> None:
        """The Token list of the current network: the native coin, its ready-made stablecoins and a custom ERC-20."""
        network = self.current_network()
        previous = self.token_key() if self.token.count() else NATIVE
        self.token.blockSignals(True)
        self.token.clear()
        self.token.addItem(tr("{symbol} (native)", symbol=network.symbol), NATIVE)
        for preset in network.tokens:
            self.token.addItem(preset.label, preset.key)
        self.token.addItem(tr("Custom ERC-20"), CUSTOM)
        # A ready-made token stays selected if the new network has it; otherwise — the native coin (spec 9.19)
        keys = [self.token.itemData(i) for i in range(self.token.count())]
        self.token.setCurrentIndex(keys.index(previous) if previous in keys else 0)
        self.token.blockSignals(False)

    def _on_network(self) -> None:
        network = self.current_network()
        self._fill_tokens()
        self._on_token()
        self._update_rpc_summary()
        self.network_changed.emit(network.key)

    def _on_token(self) -> None:
        network, key = self.current_network(), self.token_key()
        if self._last_token == CUSTOM:  # leaving the custom ERC-20 — remember the address typed in
            self._custom_address = self.token_address.text()
        preset = network.preset(key)
        self.token_address.setVisible(key != NATIVE)
        self.token_address.setReadOnly(key != CUSTOM)
        self.token_address.blockSignals(True)
        self.token_address.setText(preset.address if preset else self._custom_address if key == CUSTOM else "")
        self.token_address.setCursorPosition(0)  # the address is visible from its start
        self.token_address.blockSignals(False)
        self._last_token = key
        self.set_token_info(None)
        self.range_unit.setText(show(self.token_label()) if key != CUSTOM else "")
        self._update_all_hint()
        self.token_changed.emit()

    def _on_amount_mode(self, mode: str) -> None:
        self.amount_pages.setCurrentIndex(["all", "percent", "range"].index(mode))

    def _update_all_hint(self) -> None:
        if self.token_key() == NATIVE:
            text = tr("Each wallet sends all its {symbol} except the amount for gas.",
                      symbol=self.current_network().symbol)
        elif self.token_key() == CUSTOM:
            text = tr("Each wallet sends its entire token balance.")
        else:
            text = tr("Each wallet sends its entire {token} balance.", token=self.token_label())
        self.all_hint.setText(text)
        if self.token_key() != CUSTOM:
            self.range_unit.setText(show(self.token_label()))

    def _update_rpc_summary(self) -> None:
        network = self.current_network()
        host = urlparse(self.rpc[network.key].text()).hostname or tr("not set")
        self.rpc_section.set_summary(f"{network.title}: {host}")

    # --- state -----------------------------------------------------------------------------------------

    def set_token_info(self, text: Text | None) -> None:
        self._token_info = text
        self.token_info.setText(show(text))
        self.token_info.setVisible(bool(text))

    def set_attention(self, text: Text | None) -> None:
        """A hint above Apply. While it is there, Apply is the main button of the panel."""
        self._attention = text
        self.attention.setText(show(text))
        self.attention.setVisible(bool(text))
        set_role(self.apply_button, "primary" if text else None)

    def set_locked(self, locked: bool) -> None:
        self._body_widget.setEnabled(not locked)
        self.apply_button.setEnabled(not locked)
