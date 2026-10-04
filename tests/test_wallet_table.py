"""The wallet table: addresses as DeBank links and copying, the scroll bar under the header and above the Total
row, the ↻ icon (spec 11.1, 11.2, 12.1, 12.5)."""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.i18n import t  # noqa: E402
from app.ui import wallet_table  # noqa: E402
from app.ui.theme import apply_theme  # noqa: E402
from app.ui.wallet_table import Balance, Col, Part, WalletModel, WalletRow, WalletTable, debank_url  # noqa: E402

SENDER = "0x1234567890AbcdEF1234567890aBcdef12345678"
RECIPIENT = "0x4Ce896d765DF9EbE842ABAaa45Ff8CAAf4193D7E"


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    apply_theme(application, "dark")
    return application


@pytest.fixture
def opened(monkeypatch):
    """Links the program would open in the browser."""
    urls: list[str] = []

    class Browser:
        @staticmethod
        def openUrl(url):  # noqa: N802
            urls.append(url.toString())
            return True

    monkeypatch.setattr(wallet_table, "QDesktopServices", Browser)
    return urls


def make_table(app, rows: list[WalletRow], width: int = 1200, height: int = 400) -> WalletTable:
    model = WalletModel()
    table = WalletTable(model)
    model.set_rows(rows)
    table.resize(width, height)
    table.show()
    QTest.qWait(30)
    return table


def rows(count: int = 2) -> list[WalletRow]:
    result = [WalletRow(1, "Main", SENDER, RECIPIENT, token=Balance(Decimal(5)), native=Balance(Decimal(1))),
              WalletRow(2, "Test", None, RECIPIENT, line_error=t("invalid private key"))]
    result += [WalletRow(i + 1, f"W{i + 1}", f"0x{i:040x}", RECIPIENT, token=Balance(Decimal(5)),
                         native=Balance(Decimal(1))) for i in range(2, count)]
    return result


def click(table: WalletTable, row: int, col: Col, part: Part) -> None:
    rect = table.visualRect(table.model().index(row, col))
    delegate = table.itemDelegate()
    if part is Part.RETRY:
        point = delegate.retry_rect(rect).center().toPoint()
    else:
        _, text, icon = delegate.address_layout(rect, table.model().rows[row].link_address(col))
        point = (text if part is Part.LINK else icon).center().toPoint()
    assert table.target_at(point)[:3] == (row, col, part)
    QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)


def test_debank_link_is_lowercase():
    assert debank_url(SENDER) == "https://debank.com/profile/0x1234567890abcdef1234567890abcdef12345678"


def test_address_click_opens_debank_and_icon_copies_full_address(app, opened):
    table = make_table(app, rows(), width=900)  # narrow: the addresses are shortened in the middle
    delegate = table.itemDelegate()
    shown, _, _ = delegate.address_layout(table.visualRect(table.model().index(0, Col.SENDER)), SENDER)
    assert "…" in shown

    click(table, 0, Col.SENDER, Part.LINK)
    click(table, 0, Col.RECIPIENT, Part.LINK)
    assert opened == [debank_url(SENDER), debank_url(RECIPIENT)]

    click(table, 0, Col.SENDER, Part.COPY)
    assert QGuiApplication.clipboard().text() == SENDER
    click(table, 0, Col.RECIPIENT, Part.COPY)
    assert QGuiApplication.clipboard().text() == RECIPIENT
    assert not table.model().rows[0].checked  # a click on an address does not touch the checkbox


def test_links_work_during_mailing(app, opened):
    table = make_table(app, rows())
    table.model().locked = True
    click(table, 0, Col.RECIPIENT, Part.LINK)
    assert opened == [debank_url(RECIPIENT)]


def test_row_with_error_has_no_links(app, opened):
    table = make_table(app, rows())
    row = table.model().rows[1]
    assert row.link_address(Col.SENDER) is None and row.link_address(Col.RECIPIENT) is None
    QGuiApplication.clipboard().setText("before the click")
    rect = table.visualRect(table.model().index(1, Col.RECIPIENT))
    for x in range(rect.left(), rect.right(), 4):
        point = QPoint(x, rect.center().y())
        assert table.target_at(point) is None
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    assert opened == [] and QGuiApplication.clipboard().text() == "before the click"


def test_retry_icon_asks_to_poll_the_wallet_again(app):
    data = rows(3)
    data[2].token = data[2].native = Balance(error="429")
    table = make_table(app, data)
    model = table.model()
    requested: list[list[int]] = []
    model.retry_requested.connect(requested.append)
    point = table.itemDelegate().retry_rect(table.visualRect(model.index(2, Col.TOKEN))).center().toPoint()
    assert table.target_at(point) is None  # unavailable until Apply finished
    model.retry_enabled = True
    click(table, 2, Col.TOKEN, Part.RETRY)
    assert requested == [[2]] and model.failed_rows() == [2]


def test_scrollbar_starts_below_header_and_ends_above_the_total_row(app):
    table = make_table(app, rows(40), height=400)
    header, bar, footer = table.horizontalHeader(), table.verticalScrollBar(), table.footer
    assert bar.isVisible() and header.property("scrollbar") is True and footer.isVisible()
    header_bottom = header.mapTo(table, QPoint(0, header.height())).y()
    bar_top = bar.mapTo(table, QPoint(0, 0)).y()
    bar_bottom = bar.mapTo(table, QPoint(0, bar.height())).y()
    footer_top = footer.mapTo(table, QPoint(0, 0)).y()
    assert bar_top >= header_bottom and bar_bottom <= footer_top
    corner = table._corner
    assert corner.isVisible() and corner.height() == header.height()
    assert corner.mapTo(table, QPoint(0, 0)).y() == header.mapTo(table, QPoint(0, 0)).y()
    assert corner.mapTo(table, QPoint(0, 0)).x() == header.mapTo(table, QPoint(header.width(), 0)).x()
    assert table._footer_corner.mapTo(table, QPoint(0, 0)).y() == footer_top  # the row goes on under the bar

    # The last wallet scrolls out from under the Total row
    bar.setValue(bar.maximum())
    QTest.qWait(30)
    last = table.visualRect(table.model().index(39, 0))
    assert last.bottom() < table.viewport().height() - table.footer_height() + 1

    table.model().set_rows(rows(2))  # the bar is gone — the header's last column is rounded again
    QTest.qWait(50)  # rows are laid out by a timer
    assert not bar.isVisible() and not corner.isVisible() and header.property("scrollbar") is False


def test_total_row_shows_the_sums_and_hides_without_wallets(app):
    table = make_table(app, rows(4))
    label, token_sum, native_sum, note = table.footer._texts()
    assert label == "Total: 3 wallets" and token_sum == "15.00" and native_sum == "3.0000" and note is None
    table.model().set_rows([])
    QTest.qWait(30)
    assert not table.footer.isVisible() and table.footer_height() == 0


def test_address_columns_never_collapse(app):
    for width in (700, 1000, 1400, 2000):
        table = make_table(app, rows(40), width=width)
        header = table.horizontalHeader()
        sender, recipient = header.sectionSize(Col.SENDER), header.sectionSize(Col.RECIPIENT)
        assert sender >= WalletTable.ADDRESS_MIN and abs(sender - recipient) <= 1
        total = sum(header.sectionSize(col) for col in Col)
        assert total == table.viewport().width() or sender == WalletTable.ADDRESS_MIN
