"""Small interface widgets."""
from __future__ import annotations

from PySide6.QtCore import QLocale, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.ui import icons, theme


def label(text: str, name: str, *, wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def repolish(widget: QWidget) -> None:
    """Re-reads the style after a dynamic property changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def set_role(button: QPushButton, role: str | None) -> None:
    """The button role: primary (the main action), danger or an ordinary one (None)."""
    button.setProperty("primary", role == "primary")
    button.setProperty("danger", role == "danger")
    repolish(button)


class ElidedLabel(QLabel):
    """A one-line label that gets an ellipsis instead of pushing the layout apart. The full text is in the tooltip.

    It asks for the width of its full text, but agrees to be narrower: then the text is shortened."""

    def __init__(self, text: str = "", name: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if name:
            self.setObjectName(name)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._full = ""
        self._tooltip: str | None = None
        self.setText(text)

    def setText(self, text: str, tooltip: str | None = None) -> None:  # noqa: N802
        """tooltip — when the tooltip should say more than the text (say, sums with every digit)."""
        self._full = text
        self._tooltip = tooltip
        self.updateGeometry()
        self._elide()

    def full_text(self) -> str:
        return self._full

    def sizeHint(self) -> QSize:  # noqa: N802
        hint = super().sizeHint()
        return QSize(self.fontMetrics().horizontalAdvance(self._full) + 4, hint.height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(min(60, self.sizeHint().width()), super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        width = max(self.width(), 1)
        shown = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight, width)
        super().setText(shown)
        self.setToolTip(self._tooltip or (self._full if shown != self._full else ""))


class Combo(QComboBox):
    """A drop-down list that does not scroll with the mouse wheel while it has no focus."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setView(QListView())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def wheelEvent(self, event) -> None:  # noqa: N802
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class DecimalSpin(QDoubleSpinBox):
    """A decimal number: takes both a dot and a comma, shows no extra zeros."""

    def __init__(self, decimals: int, minimum: float, maximum: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setLocale(QLocale.c())
        self.setDecimals(decimals)
        self.setRange(minimum, maximum)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setCorrectionMode(QAbstractSpinBox.CorrectionMode.CorrectToNearestValue)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def validate(self, text: str, pos: int):
        return super().validate(text.replace(",", "."), pos)

    def valueFromText(self, text: str) -> float:  # noqa: N802
        return super().valueFromText(text.replace(",", "."))

    def textFromValue(self, value: float) -> str:  # noqa: N802
        text = f"{value:.{self.decimals()}f}"
        return text.rstrip("0").rstrip(".") if "." in text else text

    def wheelEvent(self, event) -> None:  # noqa: N802
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class IntSpin(QSpinBox):
    def __init__(self, minimum: int, maximum: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setRange(minimum, maximum)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event) -> None:  # noqa: N802
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


COMPACT_HEIGHT = 28  # the RU | EN switch and the theme button: one height that does not depend on the font (spec 13.3)


class Segmented(QWidget):
    """A switch of several buttons: exactly one is selected. compact — small buttons that keep their size."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent: QWidget | None = None, *,
                 compact: bool = False) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._group = QButtonGroup(self)
        self._buttons: dict[str, QPushButton] = {}
        policy = QSizePolicy.Policy.Fixed if compact else QSizePolicy.Policy.Expanding
        for i, (key, text) in enumerate(options):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setSizePolicy(policy, QSizePolicy.Policy.Fixed)
            button.setProperty("seg", True)
            button.setProperty("compact", compact)
            button.setProperty("segpos", "first" if i == 0 else "last" if i == len(options) - 1 else "middle")
            if compact:
                button.setFixedHeight(COMPACT_HEIGHT)
            button.toggled.connect(lambda on, k=key: on and self.changed.emit(k))
            self._group.addButton(button)
            layout.addWidget(button)
            self._buttons[key] = button
        next(iter(self._buttons.values())).setChecked(True)
        if compact:
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def value(self) -> str:
        return next(key for key, button in self._buttons.items() if button.isChecked())

    def set_value(self, key: str) -> None:
        self._buttons[key].setChecked(True)

    def set_texts(self, texts: dict[str, str]) -> None:
        for key, text in texts.items():
            self._buttons[key].setText(text)


class Collapsible(QWidget):
    """A section that opens on a click on its title. When closed, it shows a short summary."""

    def __init__(self, title: str, content: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._content = content
        self._header = QToolButton()
        self._header.setObjectName("Collapse")
        self._header.setText(title)
        self._header.setCheckable(True)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._summary = ElidedLabel(name="Hint")
        self._summary.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._summary.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(12)
        head.addWidget(self._header, 0, Qt.AlignmentFlag.AlignLeft)
        head.addWidget(self._summary, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addLayout(head)
        layout.addWidget(content)

        self._header.toggled.connect(self._set_open)
        self._set_open(False)

    def _set_open(self, is_open: bool) -> None:
        self._content.setVisible(is_open)
        self._summary.setVisible(not is_open)
        self.refresh_icon()

    def refresh_icon(self) -> None:
        """The arrow is drawn in the current theme's color."""
        self._header.setIcon(icons.chevron_icon(theme.MUTED, down=self._header.isChecked()))

    def set_open(self, is_open: bool) -> None:
        self._header.setChecked(is_open)

    def set_title(self, title: str) -> None:
        self._header.setText(title)

    def set_summary(self, text: str) -> None:
        self._summary.setText(text)


class NetworkBand(QWidget):
    """A band of the network color above the table. During polling and mailing it shows the progress."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(3)
        self._color = QColor("#8E99AA")
        self._progress: float | None = None

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def set_progress(self, value: float | None) -> None:
        self._progress = value
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        rect = self.rect()
        if self._progress is None:
            painter.fillRect(rect, self._color)
            return
        track = QColor(self._color)
        track.setAlpha(60)
        painter.fillRect(rect, track)
        done = QRect(rect)
        done.setWidth(round(rect.width() * max(0.0, min(1.0, self._progress))))
        painter.fillRect(done, self._color)


class Pill(QFrame):
    """A badge in the header: a dot of the network color, a name and an explanation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Pill")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 14, 6)
        layout.setSpacing(8)
        self._dot = QLabel()
        self._dot.setFixedSize(10, 10)
        self._main = QLabel()
        self._sub = label("", "PillSub")
        layout.addWidget(self._dot)
        layout.addWidget(self._main)
        layout.addWidget(self._sub)

    def set(self, main: str, sub: str = "", color: str | None = None, *, mono_sub: bool = False) -> None:
        self._main.setText(main)
        self._sub.setText(sub)
        self._sub.setVisible(bool(sub))
        self._sub.setFont(theme.mono_font() if mono_sub else theme.ui_font())
        self._dot.setVisible(color is not None)
        if color:
            self._dot.setPixmap(icons.dot_icon(color).pixmap(10, 10))
