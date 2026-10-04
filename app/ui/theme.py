"""Palettes, fonts and the interface style; the dark and the light theme (spec 12.3).

Color carries meaning in the interface: it is either the network color or the outcome of a transaction.
Everything else is shades of graphite; the main button stands out — light in the dark theme, dark in the light one.

Colors are read as theme.TEXT, theme.MUTED and so on at paint time: the module gives the value of the current
palette, so after a theme switch everything is simply painted again.
"""
from __future__ import annotations

import ctypes
import sys
from dataclasses import asdict, dataclass
from string import Template

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from app.ui import icons


@dataclass(frozen=True)
class Palette:
    name: str
    BG: str  # the main area
    SIDEBAR: str  # the settings panel and dialogs
    SURFACE: str  # fields and buttons
    SURFACE_HOVER: str
    SURFACE_PRESSED: str
    INPUT_DISABLED: str
    BUTTON_DISABLED: str
    BORDER: str
    BORDER_HOVER: str
    INPUT_BORDER_DISABLED: str
    BUTTON_BORDER_DISABLED: str
    TEXT: str
    MUTED: str
    FAINT: str
    PAPER: str  # the main button
    PAPER_TEXT: str
    PAPER_HOVER: str
    PRIMARY_DISABLED: str
    PRIMARY_DISABLED_TEXT: str
    DANGER_BORDER: str
    DANGER_HOVER: str
    SELECTION: str
    SEG_CHECKED: str
    SCROLL: str
    SCROLL_HOVER: str
    TABLE_BG: str
    ROW_ALT: str
    ROW_HOVER: str
    HEADER_BG: str  # the table header and the Total row
    TOOLTIP_BG: str
    LOG_BG: str
    POPUP_BG: str
    OK: str
    ERROR: str
    WARN: str
    PROGRESS: str
    QUEUED: str


DARK = Palette(
    name="dark",
    BG="#171C23",
    SIDEBAR="#1C222B",
    SURFACE="#232A35",
    SURFACE_HOVER="#2A3240",
    SURFACE_PRESSED="#313A49",
    INPUT_DISABLED="#1F252E",
    BUTTON_DISABLED="#1E242D",
    BORDER="#2F3846",
    BORDER_HOVER="#3C4757",
    INPUT_BORDER_DISABLED="#29313D",
    BUTTON_BORDER_DISABLED="#262E39",
    TEXT="#E6EAF0",
    MUTED="#8E99AA",
    FAINT="#5F6A7B",
    PAPER="#EEF1F5",
    PAPER_TEXT="#171C23",
    PAPER_HOVER="#FFFFFF",
    PRIMARY_DISABLED="#343C49",
    PRIMARY_DISABLED_TEXT="#6C7788",
    DANGER_BORDER="#5B3440",
    DANGER_HOVER="#2A1F27",
    SELECTION="#3A4A66",
    SEG_CHECKED="#3A4453",
    SCROLL="#3A4453",
    SCROLL_HOVER="#4A5566",
    TABLE_BG="#171C23",
    ROW_ALT="#1A2028",
    ROW_HOVER="#212936",
    HEADER_BG="#1C222B",
    TOOLTIP_BG="#0F1318",
    LOG_BG="#141920",
    POPUP_BG="#202733",
    OK="#5BD69A",
    ERROR="#F2727A",
    WARN="#F0B65A",
    PROGRESS="#6AA9F4",
    QUEUED="#B6C0CE",
)

# Text colors are at least 4.5:1 against every light background they appear on (WCAG AA), network colors —
# at least 3:1 (spec 12.3)
LIGHT = Palette(
    name="light",
    BG="#F3F5F8",
    SIDEBAR="#FAFBFC",
    SURFACE="#FFFFFF",
    SURFACE_HOVER="#F0F3F7",
    SURFACE_PRESSED="#E4E9EF",
    INPUT_DISABLED="#F1F3F6",
    BUTTON_DISABLED="#F1F3F6",
    BORDER="#D5DBE3",
    BORDER_HOVER="#B9C3CF",
    INPUT_BORDER_DISABLED="#E3E7EC",
    BUTTON_BORDER_DISABLED="#E3E7EC",
    TEXT="#151A21",
    MUTED="#5A6576",
    FAINT="#858F9E",
    PAPER="#1C232C",
    PAPER_TEXT="#FFFFFF",
    PAPER_HOVER="#2D3743",
    PRIMARY_DISABLED="#DCE1E8",
    PRIMARY_DISABLED_TEXT="#858F9E",
    DANGER_BORDER="#EBB8BE",
    DANGER_HOVER="#FCEFF0",
    SELECTION="#CFE0FA",
    SEG_CHECKED="#E2E7EE",
    SCROLL="#C5CDD8",
    SCROLL_HOVER="#A8B3C2",
    TABLE_BG="#FFFFFF",
    ROW_ALT="#F7F9FB",
    ROW_HOVER="#EEF3F9",
    HEADER_BG="#F0F3F7",
    TOOLTIP_BG="#FFFFFF",
    LOG_BG="#FFFFFF",
    POPUP_BG="#FFFFFF",
    OK="#16784A",
    ERROR="#C2303B",
    WARN="#975700",
    PROGRESS="#1E5FC0",
    QUEUED="#5A6576",
)

PALETTES = {DARK.name: DARK, LIGHT.name: LIGHT}
_current = DARK

# Segoe UI is the Windows system font with full Cyrillic (spec 13.2); Consolas is for addresses, hashes and the log
UI_FAMILY = "Segoe UI"
MONO_FAMILY = "Consolas"

# Widget classes that get their own system font from Qt on Windows (Segoe UI 9 pt, regular): drop-down lists, menus,
# tooltips, message boxes… QApplication.setFont(font) does not change them, so the font is set for each (spec 13.2)
SYSTEM_FONT_CLASSES = (
    "QAbstractItemView", "QListView", "QHeaderView", "QListBox", "QComboMenuItem", "QComboLineEdit", "QMenu",
    "QMenuBar", "QMenuItem", "QTipLabel", "QMessageBox", "QMessageBoxLabel", "QLabel", "QPushButton", "QToolButton",
    "QCheckBox", "QRadioButton", "QStatusBar", "QDockWidgetTitle", "QMdiSubWindowTitleBar",
)


def __getattr__(name: str) -> str:
    """theme.TEXT, theme.MUTED… — the color of the current palette."""
    if name.isupper() and name in Palette.__dataclass_fields__:
        return getattr(_current, name)
    raise AttributeError(name)


def current() -> Palette:
    return _current


def is_dark() -> bool:
    return _current is DARK


def network_color(network) -> str:
    """The network color in the current theme: in the light one a darker shade, visible on white."""
    return network.color if is_dark() else network.light_color


_QSS = Template("""
QToolTip { background: $TOOLTIP_BG; color: $TEXT; border: 1px solid $BORDER; padding: 6px 8px; }

QLabel { background: transparent; color: $TEXT; }
QLabel#Wordmark { font-size: 20px; font-weight: 700; }
QLabel#Version { color: $FAINT; font-size: 13px; }
QLabel#SectionTitle { font-size: 15px; font-weight: 700; }
QLabel#FieldLabel { color: $MUTED; font-size: 13px; }
QLabel#Hint { color: $MUTED; font-size: 13px; }
QLabel#Unit { color: $MUTED; }
QLabel#TokenInfo { color: $OK; font-size: 13px; }
QLabel#DirtyHint { color: $WARN; font-size: 13px; }
QLabel#Warning { color: $WARN; }
QLabel#PageTitle { font-size: 23px; font-weight: 700; }
QLabel#Counter { color: $MUTED; }
QLabel#RunStatus { color: $PROGRESS; }
QLabel#PanelTitle { color: $MUTED; font-size: 13px; font-weight: 700; }
QLabel#DialogTitle { font-size: 21px; font-weight: 700; }
QLabel#PillSub { color: $MUTED; }
QLabel#MonoValue { font-family: "$MONO_FAMILY"; font-size: 13px; font-weight: 700; color: $MUTED; }

QFrame#Central, QFrame#Main { background: $BG; }
QFrame#Sidebar { background: $SIDEBAR; border: none; border-right: 1px solid $BORDER; }
QWidget#SidebarBody, QWidget#SidebarHead { background: $SIDEBAR; }
QFrame#SidebarFooter { background: $SIDEBAR; border: none; border-top: 1px solid $BORDER; }
QScrollArea { background: $SIDEBAR; border: none; }
QFrame#Pill { background: $SURFACE; border: 1px solid $BORDER; border-radius: 15px; }
QFrame#LogFrame { background: $LOG_BG; border: 1px solid $BORDER; border-radius: 10px; }
QDialog#Dialog { background: $SIDEBAR; }
QFrame#SummaryBox { background: $BG; border: 1px solid $BORDER; border-radius: 10px; }

QLineEdit, QComboBox, QAbstractSpinBox {
    background: $SURFACE; color: $TEXT; border: 1px solid $BORDER; border-radius: 7px;
    padding: 6px 10px; min-height: 22px; selection-background-color: $SELECTION; selection-color: $TEXT;
}
QLineEdit:hover, QComboBox:hover, QAbstractSpinBox:hover { border-color: $BORDER_HOVER; }
QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus { border-color: $MUTED; }
QLineEdit:read-only { background: transparent; color: $MUTED; border-style: dashed; }
QLineEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled {
    color: $FAINT; background: $INPUT_DISABLED; border-color: $INPUT_BORDER_DISABLED;
}
/* 11 px: Consolas is 7 px wide per character at both 12 and 13 px, and the contract address would not fit */
QLineEdit#Mono { font-family: "$MONO_FAMILY"; font-size: 11px; font-weight: 700; }
QComboBox::drop-down { border: none; width: 28px; }
QComboBox::down-arrow { image: url("$CHEVRON"); width: 10px; height: 10px; }
QComboBox::down-arrow:disabled { image: url("$CHEVRON_FAINT"); }
QComboBox QAbstractItemView {
    background: $POPUP_BG; color: $TEXT; border: 1px solid $BORDER; outline: 0; padding: 4px;
    selection-background-color: $SURFACE_HOVER; selection-color: $TEXT;
}
QComboBox QAbstractItemView::item { min-height: 30px; padding: 0 8px; }

QPushButton {
    background: $SURFACE; color: $TEXT; border: 1px solid $BORDER; border-radius: 8px;
    padding: 8px 16px;
}
QPushButton:hover { background: $SURFACE_HOVER; }
QPushButton:pressed { background: $SURFACE_PRESSED; }
QPushButton:disabled { color: $FAINT; background: $BUTTON_DISABLED; border-color: $BUTTON_BORDER_DISABLED; }
QPushButton[primary="true"] { background: $PAPER; color: $PAPER_TEXT; border-color: $PAPER; font-weight: 700; }
QPushButton[primary="true"]:hover { background: $PAPER_HOVER; border-color: $PAPER_HOVER; }
QPushButton[primary="true"]:disabled {
    background: $PRIMARY_DISABLED; color: $PRIMARY_DISABLED_TEXT; border-color: $PRIMARY_DISABLED;
}
QPushButton[danger="true"] { color: $ERROR; background: transparent; border-color: $DANGER_BORDER; }
QPushButton[danger="true"]:hover { background: $DANGER_HOVER; }
QPushButton[danger="true"]:disabled { color: $FAINT; background: transparent; border-color: $BUTTON_BORDER_DISABLED; }

QPushButton[seg="true"] {
    background: $SURFACE; color: $MUTED; border: 1px solid $BORDER; border-radius: 0; padding: 7px 6px;
}
QPushButton[segpos="first"] { border-top-left-radius: 7px; border-bottom-left-radius: 7px; }
QPushButton[segpos="middle"] { border-left: none; }
QPushButton[segpos="last"] { border-left: none; border-top-right-radius: 7px; border-bottom-right-radius: 7px; }
QPushButton[seg="true"]:hover { color: $TEXT; }
QPushButton[seg="true"]:checked { background: $SEG_CHECKED; color: $TEXT; }
QPushButton[seg="true"]:disabled { color: $FAINT; background: $INPUT_DISABLED; }
QPushButton[compact="true"] { padding: 4px 9px; font-size: 13px; }

QToolButton#Collapse {
    background: transparent; border: none; color: $TEXT; font-size: 15px; font-weight: 700; padding: 0;
}
QToolButton#ThemeToggle {
    background: $SURFACE; border: 1px solid $BORDER; border-radius: 7px; padding: 0;
}
QToolButton#ThemeToggle:hover { background: $SURFACE_HOVER; border-color: $BORDER_HOVER; }

QTableView {
    background: $TABLE_BG; alternate-background-color: $ROW_ALT; color: $TEXT;
    border: 1px solid $BORDER; border-radius: 10px; gridline-color: transparent; outline: 0;
}
QTableView::item { border: none; padding: 0; }
QHeaderView { background: transparent; border: none; }
QHeaderView::section {
    background: $HEADER_BG; color: $MUTED; border: none; border-bottom: 1px solid $BORDER;
    padding: 0 10px; height: 36px; font-size: 13px; font-weight: 700;
}
QHeaderView::section:first { border-top-left-radius: 10px; }
QHeaderView::section:last { border-top-right-radius: 10px; }
QHeaderView[scrollbar="true"]::section:last { border-top-right-radius: 0; }
/* The corner where the two scroll bars meet: without this Qt draws a separate square with a frame (spec 12.4) */
QAbstractScrollArea::corner { background: transparent; border: none; }

QTextBrowser#Log { background: transparent; border: none; color: $TEXT; }

QSplitter::handle:vertical { background: transparent; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 4px 2px; }
QScrollBar::handle:vertical { background: $SCROLL; border-radius: 3px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background: $SCROLL_HOVER; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px 4px; }
QScrollBar::handle:horizontal { background: $SCROLL; border-radius: 3px; min-width: 32px; }
QScrollBar::handle:horizontal:hover { background: $SCROLL_HOVER; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
""")


# Body text is semi-bold, titles, addresses and hashes are bold (spec 11.4, 13.2). Segoe UI on Windows has
# weights 300, 350, 400, 600, 700 and 900: an intermediate weight (say, 500) silently turns into another one.
def ui_font(px: int = 14, weight: QFont.Weight = QFont.Weight.DemiBold, *, tabular: bool = False) -> QFont:
    """tabular — digits of one width, for balances and sums in columns: in Segoe UI Semibold "1" is narrower than
    the other digits (spec 13.2)."""
    font = QFont(UI_FAMILY)
    font.setPixelSize(px)
    font.setWeight(weight)
    if tabular:
        font.setFeature(QFont.Tag("tnum"), 1)
    return font


def mono_font(px: int = 13, weight: QFont.Weight = QFont.Weight.Bold) -> QFont:
    font = QFont(MONO_FAMILY)
    font.setPixelSize(px)
    font.setWeight(weight)  # explicitly: otherwise the weight is inherited from the window
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


def _pick_families() -> None:
    """If the fonts are missing (an old Windows), take the standard ones."""
    global UI_FAMILY, MONO_FAMILY
    families = set(QFontDatabase.families())
    if UI_FAMILY not in families:
        UI_FAMILY = "Arial"
    if MONO_FAMILY not in families:
        MONO_FAMILY = "Courier New"


def _palette() -> QPalette:
    p = _current
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: p.BG,
        QPalette.ColorRole.WindowText: p.TEXT,
        QPalette.ColorRole.Base: p.SURFACE,
        QPalette.ColorRole.AlternateBase: p.ROW_ALT,
        QPalette.ColorRole.Text: p.TEXT,
        QPalette.ColorRole.Button: p.SURFACE,
        QPalette.ColorRole.ButtonText: p.TEXT,
        QPalette.ColorRole.Highlight: p.SELECTION,
        QPalette.ColorRole.HighlightedText: p.TEXT,
        QPalette.ColorRole.ToolTipBase: p.TOOLTIP_BG,
        QPalette.ColorRole.ToolTipText: p.TEXT,
        QPalette.ColorRole.PlaceholderText: p.FAINT,
        QPalette.ColorRole.Link: p.TEXT,
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(p.FAINT))
    return palette


def apply_theme(app: QApplication, name: str | None = None) -> None:
    """Applies the theme to the whole program; without a name — the current one (dark at start)."""
    global _current
    if name is not None:
        _current = PALETTES[name]
    _pick_families()
    app.setStyle("Fusion")
    app.setPalette(_palette())
    app.setFont(ui_font())
    tokens = {**asdict(_current), "UI_FAMILY": UI_FAMILY, "MONO_FAMILY": MONO_FAMILY}
    app.setStyleSheet(_QSS.substitute(
        tokens,
        # A file per theme: Qt caches images from the style by file name
        CHEVRON=icons.chevron_asset(f"chevron-down-{_current.name}", _current.MUTED),
        CHEVRON_FAINT=icons.chevron_asset(f"chevron-down-faint-{_current.name}", _current.FAINT),
    ))
    # After the style sheet: setting it fills the per-class fonts from the system again. Only the classes that got
    # another font: each change goes through every widget of the program
    font = ui_font()
    for name in SYSTEM_FONT_CLASSES:
        if QApplication.font(name) != font:
            app.setFont(font, name)


def style_titlebar(widget: QWidget) -> None:
    """The Windows title bar in the colors of the theme (does nothing on other systems)."""
    if sys.platform != "win32":
        return
    try:
        dwm = ctypes.windll.dwmapi
        hwnd = ctypes.c_void_p(int(widget.winId()))
        dark = ctypes.c_int(1 if is_dark() else 0)
        # 20 — DWMWA_USE_IMMERSIVE_DARK_MODE, on early Windows 10 builds — 19
        if dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark)) != 0:
            dwm.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(dark), ctypes.sizeof(dark))
        color = QColor(_current.SIDEBAR)
        colorref = ctypes.c_int(color.red() | (color.green() << 8) | (color.blue() << 16))
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(colorref), ctypes.sizeof(colorref))  # caption, Windows 11
    except (AttributeError, OSError):
        pass
