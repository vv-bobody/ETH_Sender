"""The wallet table: the model, cell painting, clicks on checkboxes, addresses, hashes and retries, and the Total row
(spec 4.4, 11.1, 11.2, 12.1, 12.5)."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal
from enum import Enum, IntEnum

from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, QPoint, QPointF, QRectF, Qt, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QStyledItemDelegate, QTableView, QToolTip, QWidget

from app.i18n import Text, show, tr
from app.text import short_address, short_hash
from app.totals import State as TotalState
from app.totals import Total, WalletBalance, total
from app.ui import icons, theme
from app.ui.widgets import repolish
from app.units import plain


class Col(IntEnum):
    CHECK = 0
    NUM = 1
    NAME = 2
    SENDER = 3
    RECIPIENT = 4
    TOKEN = 5
    NATIVE = 6
    STATUS = 7
    ATTEMPTS = 8
    TX = 9


class State(Enum):
    IDLE = "idle"  # did not take part in the mailing
    QUEUED = "queued"
    SENDING = "sending"
    OK = "ok"
    CHECK = "check"  # went through, but the Transfer event is missing or does not match
    UNCONFIRMED = "unconfirmed"
    ERROR = "error"
    SKIPPED = "skipped"
    STOPPED = "stopped"


# Palette color names: the colors themselves are taken at paint time, in the current theme
STATE_COLOR = {
    State.IDLE: "FAINT",
    State.QUEUED: "QUEUED",
    State.SENDING: "PROGRESS",
    State.OK: "OK",
    State.CHECK: "WARN",
    State.UNCONFIRMED: "WARN",
    State.ERROR: "ERROR",
    State.SKIPPED: "MUTED",
    State.STOPPED: "MUTED",
}


class Mark(Enum):
    """How one sending attempt ended — a dot in the Attempts column."""

    RETRY = "retry"  # failed, a retry follows
    ACTIVE = "active"  # in progress
    OK = "ok"
    WARN = "warn"  # went through with a reservation or was not confirmed
    FAIL = "fail"


MARK_COLOR = {
    Mark.RETRY: "WARN",
    Mark.ACTIVE: "PROGRESS",
    Mark.OK: "OK",
    Mark.WARN: "WARN",
    Mark.FAIL: "ERROR",
}

MAX_ATTEMPTS = 4  # 1 attempt + 3 retries (spec 5.6)


class Part(Enum):
    """A clickable part of a cell."""

    LINK = "link"  # the address itself — the profile on DeBank
    COPY = "copy"  # the Copy icon next to the address
    RETRY = "retry"  # the ↻ icon next to "error" in a balance cell — poll the wallet again (spec 12.5)


def debank_url(address: str) -> str:
    """The wallet profile on DeBank, with the address in lower case (spec 11.1)."""
    return f"https://debank.com/profile/{address.lower()}"


@dataclass
class Balance:
    value: Decimal | None = None
    loading: bool = False
    error: Text | str | None = None


@dataclass
class WalletRow:
    num: int
    name: str
    sender: str | None  # None — the key in the line could not be parsed
    recipient: str | None
    line_error: Text | None = None
    token: Balance = field(default_factory=Balance)
    native: Balance = field(default_factory=Balance)
    checked: bool = False
    state: State = State.IDLE
    status: Text | str = "—"
    detail: Text | str | None = None  # the full status text for the tooltip
    marks: list[Mark] = field(default_factory=list)
    tx_hash: str | None = None
    tx_url: str | None = None

    @property
    def valid(self) -> bool:
        return self.line_error is None

    @property
    def balance_failed(self) -> bool:
        """The balance check failed: both balances of the wallet are missing then."""
        return self.valid and self.token.error is not None

    def link_address(self, col: int) -> str | None:
        """The address link in the sender or recipient column. A row with an error has no links (spec 11.1)."""
        if not self.valid or col not in (Col.SENDER, Col.RECIPIENT):
            return None
        return self.sender if col == Col.SENDER else self.recipient

    def balance(self) -> WalletBalance:
        return WalletBalance(self.num, self.sender, self.token.value, self.native.value,
                             failed=self.balance_failed, loading=self.token.loading or self.native.loading,
                             checked=self.checked)


def format_amount(value: Decimal, min_decimals: int = 2, max_decimals: int = 6) -> str:
    """1234.5 → "1 234.50": rounded down, extra zeros removed."""
    text = f"{value.quantize(Decimal(1).scaleb(-max_decimals), rounding=ROUND_DOWN):f}"
    whole, _, frac = text.partition(".")
    frac = frac.rstrip("0").ljust(min_decimals, "0")
    whole = f"{int(whole):,}".replace(",", " ")
    return f"{whole}.{frac}" if frac else whole


TOKEN_DECIMALS = (2, 6)  # how many decimal places balances show: at least and at most
NATIVE_DECIMALS = (4, 6)


class WalletModel(QAbstractTableModel):
    ROW_ROLE = Qt.ItemDataRole.UserRole + 1
    checked_changed = Signal()
    balances_changed = Signal()  # balances or checkboxes changed: the totals have to be recalculated
    retry_requested = Signal(list)  # rows whose balances should be polled again (spec 12.5)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.rows: list[WalletRow] = []
        self.token_label: Text | str = Text("token")
        self.native_label = "ETH"
        self.locked = False  # the checkboxes do not change during the mailing
        self.retry_enabled = False  # the ↻ icons can be clicked (spec 12.5)

    def set_rows(self, rows: list[WalletRow]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()
        self.checked_changed.emit()
        self.balances_changed.emit()

    def set_labels(self, token: Text | str, native: str) -> None:
        self.token_label, self.native_label = token, native
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, Col.TOKEN, Col.NATIVE)

    def retranslate(self) -> None:
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(Col) - 1)
        self.refresh_all()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(Col)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return {
                Col.CHECK: "",
                Col.NUM: tr("#"),
                Col.NAME: tr("Name"),
                Col.SENDER: tr("Sender"),
                Col.RECIPIENT: tr("Recipient"),
                Col.TOKEN: tr("{token} balance", token=self.token_label),
                Col.NATIVE: tr("{token} balance", token=self.native_label),
                Col.STATUS: tr("Status"),
                Col.ATTEMPTS: tr("Attempts"),
                Col.TX: tr("Transaction"),
            }[Col(section)]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if section in (Col.TOKEN, Col.NATIVE):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            if section == Col.NUM:
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        if role == self.ROW_ROLE:
            return row
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(row, Col(index.column()))
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        return Qt.ItemFlag.ItemIsEnabled

    @staticmethod
    def _tooltip(row: WalletRow, col: Col) -> str | None:
        if col == Col.STATUS:
            if row.line_error:
                return tr("Line error: {error}", error=row.line_error)
            return show(row.detail or row.status)
        if col == Col.ATTEMPTS and row.marks:
            return tr("Attempts: {count} of {total} (1 attempt and up to 3 retries)", count=len(row.marks),
                      total=MAX_ATTEMPTS)
        if col == Col.NAME:
            return row.name or row.sender
        if col == Col.SENDER:
            return row.sender
        if col == Col.RECIPIENT:
            return row.recipient
        if col == Col.TOKEN:
            return show(row.token.error) or None
        if col == Col.NATIVE:
            return show(row.native.error) or None
        if col == Col.TX:
            return row.tx_url
        return None

    def refresh_row(self, row_index: int) -> None:
        self.dataChanged.emit(self.index(row_index, 0), self.index(row_index, len(Col) - 1))
        self.balances_changed.emit()

    def refresh_all(self) -> None:
        if self.rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, len(Col) - 1))
        self.balances_changed.emit()

    def toggle(self, row_index: int) -> None:
        row = self.rows[row_index]
        if not row.valid or self.locked:
            return
        row.checked = not row.checked
        index = self.index(row_index, Col.CHECK)
        self.dataChanged.emit(index, index)
        self.checked_changed.emit()
        self.balances_changed.emit()

    def set_all(self, checked: bool) -> None:
        if self.locked or not self.rows:
            return
        for row in self.rows:
            if row.valid:
                row.checked = checked
        self.dataChanged.emit(self.index(0, Col.CHECK), self.index(len(self.rows) - 1, Col.CHECK))
        self.checked_changed.emit()
        self.balances_changed.emit()

    def counts(self) -> tuple[int, int, int]:
        """Checked, valid, with an error in the line."""
        valid = [row for row in self.rows if row.valid]
        return sum(row.checked for row in valid), len(valid), len(self.rows) - len(valid)

    def totals(self, *, checked_only: bool = False) -> Total:
        """Sums of the balances (spec 12.1)."""
        return total((row.balance() for row in self.rows if row.valid and row.sender), checked_only=checked_only)

    def failed_rows(self) -> list[int]:
        """Rows whose balance check failed (spec 12.5)."""
        return [i for i, row in enumerate(self.rows) if row.balance_failed]


class WalletDelegate(QStyledItemDelegate):
    PAD = 10
    PIP = 6
    PIP_GAP = 4
    ICON = 14  # the Copy and the ↻ icons
    ICON_GAP = 6
    HIT = 4  # how far around an address or an icon a click still counts

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.ui = theme.ui_font()
        self.digits = theme.ui_font(tabular=True)  # numbers in columns line up by digit places (spec 13.2)
        self.mono = theme.mono_font()

    # --- painting ----------------------------------------------------------------------------------

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        row: WalletRow = index.data(WalletModel.ROW_ROLE)
        view = option.widget
        model: WalletModel = index.model()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if getattr(view, "hover_row", -1) == index.row():
            painter.fillRect(option.rect, QColor(theme.ROW_HOVER))
        rect = QRectF(option.rect).adjusted(self.PAD, 0, -self.PAD, 0)
        col = Col(index.column())
        hover = getattr(view, "hover_part", None)
        part = hover[2] if hover and hover[:2] == (index.row(), col) else None
        if col == Col.CHECK:
            self._paint_check(painter, QRectF(option.rect), row, model.locked)
        elif col == Col.NUM:
            self._text(painter, rect, str(row.num), theme.FAINT if not row.valid else theme.MUTED, self.digits,
                       Qt.AlignmentFlag.AlignCenter)
        elif col == Col.NAME:
            if row.name:
                self._text(painter, rect, row.name, theme.TEXT if row.valid else theme.FAINT, self.ui)
            elif row.sender:
                self._text(painter, rect, short_address(row.sender), theme.MUTED, self.mono)
        elif col in (Col.SENDER, Col.RECIPIENT):
            link = row.link_address(col)
            if link:
                self._paint_address(painter, option.rect, link, part)
            else:
                address = row.sender if col == Col.SENDER else row.recipient
                self._text(painter, rect, address or "—", theme.FAINT, self.mono, elide=Qt.TextElideMode.ElideMiddle)
        elif col in (Col.TOKEN, Col.NATIVE):
            retry = col == Col.TOKEN and model.retry_enabled
            self._paint_balance(painter, QRectF(option.rect), row, row.token if col == Col.TOKEN else row.native, col,
                                retry=retry, hover=part)
        elif col == Col.STATUS:
            if row.valid:
                self._text(painter, rect, show(row.status), getattr(theme, STATE_COLOR[row.state]), self.ui)
            else:
                self._text(painter, rect, tr("Line error: {error}", error=row.line_error), theme.ERROR, self.ui)
        elif col == Col.ATTEMPTS and row.marks:
            self._paint_attempts(painter, rect, row.marks)
        elif col == Col.TX and row.tx_hash:
            self._paint_tx(painter, rect, row.tx_hash)
        painter.restore()

    def _text(self, painter, rect, text, color, font, align=None, elide=Qt.TextElideMode.ElideRight) -> None:
        align = align or (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        painter.setFont(font)
        painter.setPen(QColor(color))
        shown = QFontMetrics(font).elidedText(text, elide, int(rect.width()))
        painter.drawText(rect, align, shown)

    def _paint_check(self, painter, cell: QRectF, row: WalletRow, locked: bool) -> None:
        c = cell.center()
        box = QRectF(c.x() - 8, c.y() - 8, 16, 16)
        if not row.valid:
            pen = QPen(QColor(theme.ERROR), 1.6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(box.left() + 4, box.top() + 4), QPointF(box.right() - 4, box.bottom() - 4))
            painter.drawLine(QPointF(box.right() - 4, box.top() + 4), QPointF(box.left() + 4, box.bottom() - 4))
            return
        if locked:
            painter.setOpacity(0.45)
        if row.checked:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme.PAPER))
            painter.drawRoundedRect(box, 4, 4)
            pen = QPen(QColor(theme.PAPER_TEXT), 1.8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            tick = QPainterPath()
            tick.moveTo(box.left() + 4, box.top() + 8.5)
            tick.lineTo(box.left() + 7, box.top() + 11.5)
            tick.lineTo(box.left() + 12, box.top() + 5)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(tick)
        else:
            painter.setPen(QPen(QColor(theme.MUTED), 1.3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(box.adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)

    def _paint_balance(self, painter, cell: QRectF, row: WalletRow, balance: Balance, col: Col, *, retry: bool,
                       hover: Part | None) -> None:
        rect = cell.adjusted(self.PAD, 0, -self.PAD, 0)
        right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        if not row.valid:
            return
        if balance.loading:
            self._text(painter, rect, "…", theme.MUTED, self.ui, right)
        elif balance.error:
            self._text(painter, rect, tr("error"), theme.ERROR, self.ui, right)
            if retry:
                icons.paint_retry(painter, self.retry_rect(cell), theme.TEXT if hover is Part.RETRY else theme.MUTED)
        elif balance.value is None:
            self._text(painter, rect, "—", theme.FAINT, self.ui, right)
        else:
            decimals = TOKEN_DECIMALS if col == Col.TOKEN else NATIVE_DECIMALS
            color = theme.FAINT if balance.value == 0 else theme.TEXT
            self._text(painter, rect, format_amount(balance.value, *decimals), color, self.digits, right)

    def retry_rect(self, cell: QRectF) -> QRectF:
        """Where the ↻ icon is: to the left of the right-aligned word "error"."""
        rect = QRectF(cell).adjusted(self.PAD, 0, -self.PAD, 0)
        width = QFontMetrics(self.ui).horizontalAdvance(tr("error"))
        left = rect.right() - width - self.ICON_GAP - self.ICON
        return QRectF(left, rect.center().y() - self.ICON / 2, self.ICON, self.ICON)

    def _paint_attempts(self, painter, rect: QRectF, marks: list[Mark]) -> None:
        """A dot for each of the 4 attempts: its color is how it ended, an empty one was not needed."""
        cy = rect.center().y()
        for i in range(MAX_ATTEMPTS):
            pip = QRectF(rect.left() + i * (self.PIP + self.PIP_GAP), cy - self.PIP / 2, self.PIP, self.PIP)
            if i < len(marks):
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(getattr(theme, MARK_COLOR[marks[i]])))
                painter.drawEllipse(pip)
            else:
                painter.setPen(QPen(QColor(theme.FAINT), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(pip.adjusted(0.5, 0.5, -0.5, -0.5))

    def _paint_tx(self, painter, rect: QRectF, tx_hash: str) -> None:
        text = short_hash(tx_hash)
        width = QFontMetrics(self.mono).horizontalAdvance(text)
        self._text(painter, rect, text, theme.TEXT, self.mono)
        self._underline(painter, rect, width, theme.FAINT)
        self._text(painter, rect.adjusted(width + 6, 0, 0, 0), "↗", theme.MUTED, self.ui)

    def _underline(self, painter, rect: QRectF, width: float, color: str) -> None:
        """A link underline below monospaced text centered in the row."""
        baseline = rect.center().y() + QFontMetrics(self.mono).ascent() / 2 + 2
        painter.setPen(QPen(QColor(color), 1))
        painter.drawLine(QPointF(rect.left(), baseline), QPointF(rect.left() + width, baseline))

    def address_layout(self, cell: QRectF, address: str) -> tuple[str, QRectF, QRectF]:
        """The address (shortened in the middle if it does not fit), its place and the place of the Copy icon."""
        rect = QRectF(cell).adjusted(self.PAD, 0, -self.PAD, 0)
        metrics = QFontMetrics(self.mono)
        room = max(0, int(rect.width()) - self.ICON - self.ICON_GAP)
        shown = metrics.elidedText(address, Qt.TextElideMode.ElideMiddle, room)
        text = QRectF(rect.left(), rect.top(), metrics.horizontalAdvance(shown), rect.height())
        icon = QRectF(text.right() + self.ICON_GAP, rect.center().y() - self.ICON / 2, self.ICON, self.ICON)
        return shown, text, icon

    def address_part(self, cell: QRectF, row: WalletRow, col: int, pos: QPointF) -> tuple[Part, QRectF] | None:
        """What is under the cursor in an address cell: the address itself or the Copy icon, and its area."""
        address = row.link_address(col)
        if not address:
            return None
        _, text, icon = self.address_layout(cell, address)
        icon = icon.adjusted(-self.HIT, -self.HIT, self.HIT, self.HIT)
        if icon.contains(pos):
            return Part.COPY, icon
        line = QFontMetrics(self.mono).height() / 2 + self.HIT
        text = QRectF(text.left(), text.center().y() - line, text.width() + self.ICON_GAP / 2, 2 * line)
        if text.contains(pos):
            return Part.LINK, text
        return None

    def hit(self, cell: QRectF, row: WalletRow, col: int, pos: QPointF, *, retry_enabled: bool
            ) -> tuple[Part, QRectF] | None:
        """A clickable part of the cell under the cursor: an address, the Copy icon or the ↻ icon."""
        if col in (Col.SENDER, Col.RECIPIENT):
            return self.address_part(cell, row, col, pos)
        if col == Col.TOKEN and retry_enabled and row.balance_failed:
            icon = self.retry_rect(cell).adjusted(-self.HIT, -self.HIT, self.HIT, self.HIT)
            if icon.contains(pos):
                return Part.RETRY, icon
        return None

    def _paint_address(self, painter, cell: QRectF, address: str, hover: Part | None) -> None:
        """The address is a link to DeBank, the Copy icon is next to it (spec 11.1)."""
        shown, text, icon = self.address_layout(cell, address)
        painter.setFont(self.mono)
        painter.setPen(QColor(theme.TEXT))
        painter.drawText(text, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                         | int(Qt.TextFlag.TextDontClip), shown)
        self._underline(painter, text, text.width(), theme.MUTED if hover is Part.LINK else theme.FAINT)
        self._paint_copy(painter, icon, theme.TEXT if hover is Part.COPY else theme.MUTED)

    @staticmethod
    def _paint_copy(painter, box: QRectF, color: str) -> None:
        """The Copy icon: two sheets, the back one peeks out at a corner."""
        pen = QPen(QColor(color), 1.3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        x, y = box.left(), box.top()
        back = QPainterPath()
        back.moveTo(x + 2, y + 9.5)
        back.lineTo(x + 2, y + 3.8)
        back.quadTo(x + 2, y + 2, x + 3.8, y + 2)
        back.lineTo(x + 9.5, y + 2)
        painter.drawPath(back)
        painter.drawRoundedRect(QRectF(x + 5, y + 5, 7.5, 7.5), 1.8, 1.8)

    # --- clicks ----------------------------------------------------------------------------------------

    def editorEvent(self, event, model, option, index) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            row: WalletRow = index.data(WalletModel.ROW_ROLE)
            if index.column() in (Col.CHECK, Col.NUM, Col.NAME):
                model.toggle(index.row())
                return True
            if index.column() == Col.TX and row.tx_url:
                QDesktopServices.openUrl(QUrl(row.tx_url))
                return True
            # Addresses are only for viewing, so they work during the mailing too (spec 11.1)
            hit = self.hit(QRectF(option.rect), row, index.column(), event.position(),
                           retry_enabled=model.retry_enabled)
            if hit:
                part, area = hit
                if part is Part.RETRY:
                    model.retry_requested.emit([index.row()])
                elif part is Part.LINK:
                    QDesktopServices.openUrl(QUrl(debank_url(row.link_address(index.column()))))
                else:
                    copy_address(row.link_address(index.column()), event.globalPosition().toPoint(), option.widget,
                                 area)
                return True
        return super().editorEvent(event, model, option, index)


def copy_address(address: str, at: QPoint, view: QAbstractItemView | None, area: QRectF) -> None:
    """The full address goes to the clipboard, and a "Copied" tooltip appears next to the cursor."""
    QGuiApplication.clipboard().setText(address)
    if view is not None:
        QToolTip.showText(at, tr("Copied"), view.viewport(), area.toAlignedRect(), 1500)


def _round_corners(rect: QRectF, radius: float, *, top_right: bool = False, bottom_left: bool = False,
                   bottom_right: bool = False) -> QPainterPath:
    """A rectangle with only the given corners rounded."""
    r = min(radius, rect.width(), rect.height())
    path = QPainterPath()
    path.moveTo(rect.left(), rect.top())
    if top_right:
        path.lineTo(rect.right() - r, rect.top())
        path.arcTo(QRectF(rect.right() - 2 * r, rect.top(), 2 * r, 2 * r), 90, -90)
    else:
        path.lineTo(rect.right(), rect.top())
    if bottom_right:
        path.lineTo(rect.right(), rect.bottom() - r)
        path.arcTo(QRectF(rect.right() - 2 * r, rect.bottom() - 2 * r, 2 * r, 2 * r), 0, -90)
    else:
        path.lineTo(rect.right(), rect.bottom())
    if bottom_left:
        path.lineTo(rect.left() + r, rect.bottom())
        path.arcTo(QRectF(rect.left(), rect.bottom() - 2 * r, 2 * r, 2 * r), 270, -90)
    else:
        path.lineTo(rect.left(), rect.bottom())
    path.closeSubpath()
    return path


RADIUS = 10  # as the table frame and the header's last column in the style


class HeaderCorner(QWidget):
    """The header above the vertical scroll bar: the bar starts below the header, and the header spans the whole
    table width with its rounded top right corner (spec 11.2)."""

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        painter.fillPath(_round_corners(rect, RADIUS, top_right=True), QColor(theme.HEADER_BG))
        painter.fillRect(QRectF(rect.left(), rect.bottom() - 1, rect.width(), 1), QColor(theme.BORDER))


class FooterCorner(QWidget):
    """The Total row below the vertical scroll bar: the bar ends above the row (spec 12.1)."""

    def __init__(self, table: WalletTable) -> None:
        super().__init__()
        self.table = table

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        rounded = not self.table.horizontalScrollBar().isVisible()  # otherwise the horizontal bar is below
        painter.fillPath(_round_corners(rect, RADIUS, bottom_right=rounded), QColor(theme.HEADER_BG))
        painter.fillRect(QRectF(rect.left(), rect.top(), rect.width(), 1), QColor(theme.BORDER))


class TotalsFooter(QWidget):
    """The Total row at the bottom of the table: sums under the balance columns (spec 12.1).

    It lies over the bottom of the rows area, does not move when the rows scroll and moves with the columns
    when the table scrolls horizontally."""

    PAD = 10

    def __init__(self, table: WalletTable) -> None:
        super().__init__(table)
        self.table = table
        self.label_font = theme.ui_font(13, QFont.Weight.Bold)
        self.sum_font = theme.ui_font(14, QFont.Weight.Bold, tabular=True)

    # Where things are, in the footer's coordinates: they match the coordinates of the rows area
    def _column(self, col: Col) -> QRectF | None:
        header = self.table.horizontalHeader()
        if header.isSectionHidden(col):
            return None
        return QRectF(header.sectionViewportPosition(col), 0, header.sectionSize(col), self.height())

    def _note_rect(self) -> QRectF:
        header = self.table.horizontalHeader()
        left = header.sectionViewportPosition(Col.STATUS)
        return QRectF(left + self.PAD, 0, max(0, self.width() - left - 2 * self.PAD), self.height())

    def _texts(self) -> tuple[str, str | None, str | None, str | None]:
        """The label, the token sum, the native coin sum (None — its column is hidden) and the note."""
        model: WalletModel = self.table.model()
        totals = model.totals()
        native_shown = not self.table.horizontalHeader().isSectionHidden(Col.NATIVE)
        if totals.state is TotalState.EMPTY:
            return tr("Total"), "—", "—" if native_shown else None, None
        if totals.state is TotalState.LOADING:
            return tr("Total"), "…", "…" if native_shown else None, None
        note = tr("{count:wallets} excluded: balance check failed", count=len(totals.failed)) if totals.failed else None
        return (tr("Total: {count:wallets}", count=totals.wallets), format_amount(totals.token, *TOKEN_DECIMALS),
                format_amount(totals.native, *NATIVE_DECIMALS) if native_shown else None, note)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        bottom = not self.table.horizontalScrollBar().isVisible()  # the row touches the bottom of the frame
        alone = not self.table.verticalScrollBar().isVisible()  # nothing to the right: the corner is ours
        painter.fillPath(_round_corners(rect, RADIUS, bottom_left=bottom, bottom_right=bottom and alone),
                         QColor(theme.HEADER_BG))
        painter.fillRect(QRectF(rect.left(), rect.top(), rect.width(), 1), QColor(theme.BORDER))

        label, token_sum, native_sum, note = self._texts()
        flags = Qt.AlignmentFlag.AlignVCenter
        num, token_col = self._column(Col.NUM), self._column(Col.TOKEN)
        if num is not None and token_col is not None:
            area = QRectF(num.left() + self.PAD, 0, max(0.0, token_col.left() - num.left() - 2 * self.PAD),
                          rect.height())
            self._text(painter, area, label, theme.MUTED, self.label_font, flags | Qt.AlignmentFlag.AlignLeft)
        empty = token_sum in ("—", "…")
        for col, text in ((Col.TOKEN, token_sum), (Col.NATIVE, native_sum)):
            cell = self._column(col)
            if cell is not None and text is not None:
                self._text(painter, cell.adjusted(self.PAD, 0, -self.PAD, 0), text,
                           theme.FAINT if empty else theme.TEXT, self.sum_font, flags | Qt.AlignmentFlag.AlignRight)
        if note:
            self._text(painter, self._note_rect(), note, theme.WARN, self.label_font, flags | Qt.AlignmentFlag.AlignLeft)

    @staticmethod
    def _text(painter, rect: QRectF, text: str, color: str, font, align) -> None:
        painter.setFont(font)
        painter.setPen(QColor(color))
        painter.drawText(rect, int(align), QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight,
                                                                           int(rect.width())))

    def tooltip_at(self, pos: QPointF) -> str | None:
        """Sums with every digit and which wallets were left out."""
        model: WalletModel = self.table.model()
        totals = model.totals()
        if totals.state is not TotalState.READY:
            return None
        for col, value, label in ((Col.TOKEN, totals.token, model.token_label),
                                  (Col.NATIVE, totals.native, model.native_label)):
            cell = self._column(col)
            if cell is not None and cell.contains(pos):
                return f"{plain(value)} {show(label)}"
        if totals.failed and self._note_rect().contains(pos):
            return tr("Balances were not loaded for wallets {numbers}. The reasons are in the log.",
                      numbers=", ".join(f"#{num}" for num in totals.failed))
        return None

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            text = self.tooltip_at(QPointF(event.pos()))
            if text:
                QToolTip.showText(event.globalPos(), text, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        event.ignore()  # the table scrolls under the wheel as if the row were not there


class WalletTable(QTableView):
    WIDTHS = {
        Col.CHECK: 40,
        Col.NUM: 40,
        Col.NAME: 130,
        Col.TOKEN: 112,
        Col.NATIVE: 104,
        Col.STATUS: 210,
        Col.ATTEMPTS: 78,
        Col.TX: 124,
    }
    ADDRESSES = (Col.SENDER, Col.RECIPIENT)
    ADDRESS_MIN = 150  # an address with its icon is unreadable when narrower: the table scrolls sideways instead

    def __init__(self, model: WalletModel, parent=None) -> None:
        super().__init__(parent)
        self.hover_row = -1
        self.hover_part: tuple[int, Col, Part] | None = None  # the row, the column and the part under the cursor
        # By default the vertical scroll bar runs along the whole height, the header and the Total row included.
        # A piece of the header goes above it and a piece of the Total row below it; while the bar is visible,
        # the header's last column loses its rounding — that piece draws it
        self._corner = HeaderCorner()
        self.addScrollBarWidget(self._corner, Qt.AlignmentFlag.AlignTop)
        self._footer_corner = FooterCorner(self)
        self.addScrollBarWidget(self._footer_corner, Qt.AlignmentFlag.AlignBottom)
        self.footer = TotalsFooter(self)
        self.setModel(model)
        self.setItemDelegate(WalletDelegate(self))
        self.setMouseTracking(True)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setWordWrap(False)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        rows = self.verticalHeader()
        rows.setVisible(False)
        rows.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        rows.setDefaultSectionSize(40)

        header = self.horizontalHeader()
        header.setHighlightSections(False)
        header.setMinimumSectionSize(36)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for col in Col:
            fixed = col in (Col.CHECK, Col.NUM, *self.ADDRESSES)
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed if fixed else QHeaderView.ResizeMode.Interactive)
            header.resizeSection(col, self.WIDTHS.get(col, self.ADDRESS_MIN))
        header.sectionResized.connect(self._on_section_resized)
        self.horizontalScrollBar().valueChanged.connect(self.footer.update)
        model.modelReset.connect(self._on_reset)
        model.balances_changed.connect(self.footer.update)
        header.setProperty("scrollbar", False)
        self.verticalScrollBar().rangeChanged.connect(self._update_corner)
        self._on_reset()

    def _on_section_resized(self, col: int, *_) -> None:
        if col not in self.ADDRESSES:
            self._fit_addresses()
        self.footer.update()

    def _on_reset(self) -> None:
        self._update_spans()
        visible = self.model().rowCount() > 0
        self.footer.setVisible(visible)
        self._footer_corner.setVisible(visible)
        self.updateGeometries()

    def _fit_addresses(self) -> None:
        """The address columns share the free width equally, but are never narrower than ADDRESS_MIN.
        The Stretch mode does not fit here: when space is short, Qt squeezes such columns to 36 px and the
        addresses disappear."""
        header = self.horizontalHeader()
        others = sum(header.sectionSize(col) for col in Col if col not in self.ADDRESSES)  # a hidden column is 0
        free = self.viewport().width() - others
        sender = max(self.ADDRESS_MIN, free // 2)
        header.resizeSection(Col.SENDER, sender)
        header.resizeSection(Col.RECIPIENT, max(self.ADDRESS_MIN, free - sender))

    def footer_height(self) -> int:
        model = self.model()  # None while setModel() is still running
        return self.horizontalHeader().height() if model is not None and model.rowCount() > 0 else 0

    def updateGeometries(self) -> None:  # noqa: N802
        super().updateGeometries()
        height = self.horizontalHeader().height()
        self._corner.setFixedHeight(height)
        self._footer_corner.setFixedHeight(height)
        self._place_footer()
        footer = self.footer_height()
        if footer:
            # The Total row covers the bottom of the rows area: the last rows must scroll out from under it
            bar = self.verticalScrollBar()
            visible = max(1, self.viewport().height() - footer)
            bar.setRange(0, max(0, self.verticalHeader().length() - visible))
            bar.setPageStep(visible)

    def _place_footer(self) -> None:
        area = self.viewport().geometry()
        height = self.horizontalHeader().height()
        self.footer.setGeometry(area.x(), area.y() + area.height() - height, area.width(), height)
        self.footer.raise_()
        self.footer.update()
        self._footer_corner.update()

    def _update_corner(self) -> None:
        bar = self.verticalScrollBar()
        scrolls = bar.maximum() > bar.minimum()
        header = self.horizontalHeader()
        if header.property("scrollbar") != scrolls:
            header.setProperty("scrollbar", scrolls)
            repolish(header)
            header.viewport().update()
        self.footer.update()

    def _update_spans(self) -> None:
        """A row with an error in wallets.txt shows its error over the empty Attempts and Transaction too."""
        self.clearSpans()
        model: WalletModel = self.model()
        for i, row in enumerate(model.rows):
            if not row.valid:
                self.setSpan(i, Col.STATUS, 1, len(Col) - Col.STATUS)

    def retheme(self) -> None:
        """Repaints everything that is drawn in code in the current theme's colors."""
        for widget in (self.viewport(), self.footer, self._corner, self._footer_corner):
            widget.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self.model().rowCount() == 0:
            painter = QPainter(self.viewport())
            painter.setPen(QColor(theme.MUTED))
            painter.setFont(theme.ui_font())
            rect = self.viewport().rect().adjusted(60, 0, -60, 0)
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap),
                             tr("No wallets yet. Add them to the wallets.txt file next to the program, one per line: "
                                "name,private key,recipient address — or without a name: private key,recipient "
                                "address. Then click Apply."))

    def target_at(self, pos: QPoint) -> tuple[int, Col, Part, QRectF] | None:
        """An address, the Copy icon or the ↻ icon at a point of the rows area."""
        index = self.indexAt(pos)
        if not index.isValid():
            return None
        row: WalletRow = index.data(WalletModel.ROW_ROLE)
        hit = self.itemDelegate().hit(QRectF(self.visualRect(index)), row, index.column(), QPointF(pos),
                                      retry_enabled=self.model().retry_enabled)
        return (index.row(), Col(index.column()), *hit) if hit else None

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position().toPoint()
        index = self.indexAt(pos)
        hover = index.row() if index.isValid() else -1
        target = self.target_at(pos)
        part = target[:3] if target else None
        if hover != self.hover_row or part != self.hover_part:
            self.hover_row, self.hover_part = hover, part
            self.viewport().update()
        clickable = target is not None
        if index.isValid() and not clickable:
            row: WalletRow = index.data(WalletModel.ROW_ROLE)
            if index.column() in (Col.CHECK, Col.NUM, Col.NAME):
                clickable = row.valid and not self.model().locked
            elif index.column() == Col.TX:
                clickable = bool(row.tx_url)
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def viewportEvent(self, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Resize:  # the window, or a scroll bar appeared or went away
            self._fit_addresses()
            self._place_footer()
        elif event.type() == QEvent.Type.Leave:
            self._clear_hover()
        elif event.type() == QEvent.Type.ToolTip:
            target = self.target_at(event.pos())
            if target and target[2] in (Part.COPY, Part.RETRY):
                text = tr("Copy address") if target[2] is Part.COPY else tr("Retry balance check")
                QToolTip.showText(event.globalPos(), text, self.viewport(), target[3].toAlignedRect())
                return True
        return super().viewportEvent(event)

    def _clear_hover(self) -> None:
        if self.hover_row != -1 or self.hover_part is not None:
            self.hover_row = -1
            self.hover_part = None
            self.viewport().update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._clear_hover()
        super().leaveEvent(event)
