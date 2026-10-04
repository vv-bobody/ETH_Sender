"""The look of version 1.3: the font, the network dot in a highlighted row, the switch heights, the retry icon and
the bridged token warning (spec 13.1, 13.2, 13.3, 13.5)."""
from __future__ import annotations

import os

import pytest
import shiboken6

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, QSize, Qt  # noqa: E402
from PySide6.QtGui import QFont, QIcon, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from app import i18n  # noqa: E402
from app.networks import NETWORKS  # noqa: E402
from app.ui import demo, icons, theme  # noqa: E402
from app.ui.confirm_dialog import ConfirmDialog  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.theme import apply_theme  # noqa: E402
from app.ui.widgets import COMPACT_HEIGHT  # noqa: E402


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    apply_theme(application, "dark")
    return application


@pytest.fixture(autouse=True)
def english_and_dark(app):
    i18n.set_language(i18n.EN)
    apply_theme(app, "dark")
    yield
    i18n.set_language(i18n.EN)
    apply_theme(app, "dark")


@pytest.fixture
def windows():
    """Main windows of a test, deleted after it: every theme change restyles all the widgets that are still alive."""
    created: list[MainWindow] = []

    def make() -> MainWindow:
        created.append(MainWindow())
        return created[-1]

    yield make
    for window in created:
        shiboken6.delete(window)


def same_font(font: QFont, px: int = 14, weight: QFont.Weight = QFont.Weight.DemiBold) -> bool:
    return (font.family(), font.pixelSize(), font.weight()) == (theme.UI_FAMILY, px, weight)


def test_interface_font_is_segoe_ui():
    assert theme.UI_FAMILY in ("Segoe UI", "Arial")  # Arial only where Windows has no Segoe UI
    assert theme.ui_font().family() == theme.UI_FAMILY and "Bahnschrift" not in (theme.UI_FAMILY, theme.MONO_FAMILY)


@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_lists_tooltips_and_message_boxes_get_the_program_font(app, windows, theme_name):
    """Qt gives these classes their own system font; the program font is set for them after the style sheet
    (spec 13.2)."""
    apply_theme(app, theme_name)
    for name in ("QAbstractItemView", "QListView", "QTipLabel", "QMessageBox", "QMenu"):
        assert same_font(QApplication.font(name)), name
    window = windows()
    assert same_font(window.settings.network.view().font())


def test_balance_digits_are_of_one_width(windows):
    font = theme.ui_font(tabular=True)
    assert font.featureValue(QFont.Tag("tnum")) == 1
    window = windows()
    assert window.table.itemDelegate().digits.featureValue(QFont.Tag("tnum")) == 1
    assert window.table.footer.sum_font.featureValue(QFont.Tag("tnum")) == 1


def test_network_dot_does_not_fade_in_a_highlighted_row(app):
    icon = icons.dot_icon(theme.network_color(NETWORKS["base"]))
    normal = icon.pixmap(QSize(10, 10), 1.0, QIcon.Mode.Normal).toImage()
    selected = icon.pixmap(QSize(10, 10), 1.0, QIcon.Mode.Selected).toImage()
    assert normal == selected


def test_language_switch_and_theme_button_are_of_one_height(app, windows):
    for language in (i18n.EN, i18n.RU):
        for theme_name in ("dark", "light"):
            i18n.set_language(language)
            apply_theme(app, theme_name)
            window = windows()
            window.show()
            app.processEvents()
            panel = window.settings
            buttons = list(panel.language._buttons.values())
            assert {button.height() for button in buttons} == {COMPACT_HEIGHT}
            assert panel.theme_button.size() == QSize(COMPACT_HEIGHT, COMPACT_HEIGHT)
            tops = {button.mapTo(window, button.rect().topLeft()).y() for button in buttons}
            tops.add(panel.theme_button.mapTo(window, panel.theme_button.rect().topLeft()).y())
            assert len(tops) == 1, (language, theme_name, tops)


def test_retry_icon_fits_its_square_at_both_scales(app):
    """The new arrowhead is filled and stays inside the 14 px icon (spec 13.1)."""
    for scale in (1, 2):
        image = QImage(14 * scale, 14 * scale, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(scale, scale)
        icons.paint_retry(painter, QRectF(0, 0, 14, 14), "#000000")
        painter.end()
        rows = [y for y in range(image.height()) if any(image.pixelColor(x, y).alpha() for x in range(image.width()))]
        assert rows and rows[-1] < image.height() - 1  # the bottom of the circle is not cut off


def warning_of(dialog: ConfirmDialog) -> str | None:
    labels = [widget for widget in dialog.findChildren(QLabel) if widget.objectName() == "Warning"]
    return labels[0].text() if labels else None


def test_bridged_token_warns_in_the_confirmation_window(app):
    summary = demo.summary()
    assert warning_of(ConfirmDialog(summary)) is None
    summary = demo.bridged_summary()
    assert warning_of(ConfirmDialog(summary)) == ("USDC.e is a bridged version of USDC. Make sure the recipient "
                                                  "addresses accept exactly this one: exchanges often credit only "
                                                  "native USDC.")
    i18n.set_language(i18n.RU)
    assert warning_of(ConfirmDialog(summary)) == ("USDC.e — мостовая версия USDC. Убедитесь, что адреса получателей "
                                                  "принимают именно её: биржи часто зачисляют только родной USDC.")
