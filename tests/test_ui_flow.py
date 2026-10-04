"""The whole path in a real window with a network in memory: files → Apply → balances → Start → statuses;
language and theme switches, polling retries and totals (spec 12)."""
from __future__ import annotations

import os
import time

import pytest
from eth_account import Account

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from app import i18n  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.confirm_dialog import ConfirmDialog  # noqa: E402
from app.ui.controller import Controller  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.theme import apply_theme  # noqa: E402
from app.ui.wallet_table import State  # noqa: E402
from tests.fake_chain import FakeChain, FakeClock  # noqa: E402

KEYS = ["0x" + f"{i + 1:02x}" * 32 for i in range(3)]
RECIPIENT = "0x4Ce896d765DF9EbE842ABAaa45Ff8CAAf4193D7E"
SETTINGS = "[main]\nnetwork = arbitrum\ntoken = native\ndelay_min = 0\ndelay_max = 0\ntx_timeout = 10\n"


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    apply_theme(application, "dark")
    return application


@pytest.fixture(autouse=True)
def english_and_dark(app):
    """Every test starts in English and the dark theme, as the program does by default."""
    i18n.set_language(i18n.EN)
    apply_theme(app, "dark")
    yield
    i18n.set_language(i18n.EN)
    apply_theme(app, "dark")


def wait_until(app, condition, timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("the condition did not come true in time")
        app.processEvents()
        time.sleep(0.01)


def start(tmp_path, chain: FakeChain, *, settings: str = SETTINGS, broken: bool = True) -> tuple[MainWindow, Controller]:
    (tmp_path / "settings.txt").write_text(settings, encoding="utf-8")
    lines = [f"W{i + 1},{key},{RECIPIENT}" for i, key in enumerate(KEYS)] + (["Сломанный,xyz,0x1"] if broken else [])
    (tmp_path / "wallets.txt").write_text("\n".join(lines), encoding="utf-8")
    window = MainWindow()
    controller = Controller(window, tmp_path / "settings.txt", tmp_path / "wallets.txt",
                            chain_factory=lambda network, url: chain)
    controller.load()
    return window, controller


def apply(app, controller: Controller) -> None:
    controller.apply()
    wait_until(app, lambda: not controller.polling)


def test_apply_then_send_from_checked_wallets(app, tmp_path, monkeypatch):
    chain = FakeChain(time.monotonic, native=10**18, mine_after=0)
    window, controller = start(tmp_path, chain)
    model = window.model
    assert len(model.rows) == 4 and not model.rows[3].valid
    assert not window.start_button.isEnabled()  # Start is unavailable before Apply

    apply(app, controller)
    assert controller.applied is not None
    assert all(row.native.value == 1 for row in model.rows[:3])
    assert not window.start_button.isEnabled()  # nothing is checked

    model.toggle(0)
    model.toggle(2)
    assert window.start_button.isEnabled()

    window.settings.edited.emit()  # a setting changed — Start is unavailable until the next Apply
    assert not window.start_button.isEnabled()
    apply(app, controller)
    assert model.counts()[0] == 0  # Apply clears the checkboxes (spec 9.14)
    model.toggle(0)
    model.toggle(2)

    shown: list = []
    monkeypatch.setattr(ConfirmDialog, "exec",
                        lambda self: (shown.append(self.findChildren(type(window.counter))), QDialog.DialogCode.Accepted)[1])
    controller.start()
    assert controller.running and not window.start_button.isEnabled()
    # The settings are locked during the mailing, the language and theme switches are not (spec 12.2, 12.3)
    assert not window.settings.network.isEnabled()
    assert window.settings.language.isEnabled() and window.settings.theme_button.isEnabled()
    assert not window.model.retry_enabled
    wait_until(app, lambda: not controller.running)

    states = [row.state for row in model.rows]
    assert states[0] is State.OK and states[2] is State.OK and states[1] is State.IDLE
    assert str(model.rows[0].status).startswith("Success: ") and model.rows[0].tx_url.startswith("https://arbiscan.io/tx/")
    senders = {Account.recover_transaction(tx["raw"]) for tx in chain.sent}
    assert len(chain.sent) == 2
    assert senders == {Account.from_key(KEYS[0]).address, Account.from_key(KEYS[2]).address}
    log = window.log.toPlainText()
    assert "Done: 2 succeeded" in log and "Arbitrum RPC responds" in log
    assert (tmp_path / "settings.txt").read_text(encoding="utf-8").startswith("# ===== ETH Sender")
    labels = [label.text() for label in shown[0]]
    assert "Balances" in labels and "2.00 ETH" in labels  # the balances of the checked wallets (spec 12.1)


def test_language_switch_translates_everything_at_once_and_saves_only_ui(app, tmp_path):
    chain = FakeChain(time.monotonic, native=10**18, mine_after=0)
    window, controller = start(tmp_path, chain)
    apply(app, controller)
    assert window.title.text() == "Wallets" and window.settings.apply_button.text() == "Apply"
    window.settings.delay_min.setValue(7)  # an unsaved edit must not get into the file

    window.settings.language.set_value("ru")  # the RU | EN switch in the panel header
    assert i18n.language() == "ru"
    assert window.title.text() == "Кошельки" and window.settings.apply_button.text() == "Применить"
    assert window.model.headerData(1, window.table.horizontalHeader().orientation()) == "№"
    log = window.log.toPlainText()
    assert "RPC Arbitrum отвечает" in log and "Балансы загружены: 3 кошелька" in log  # lines written before the switch
    assert "Ошибка в строке" in window.model._tooltip(window.model.rows[3], 7)
    assert not window.start_button.isEnabled() or controller.dirty is False  # the switch does not block Start
    assert controller.dirty  # only the delay edit made the settings dirty

    text = (tmp_path / "settings.txt").read_text(encoding="utf-8")
    assert "language = ru" in text and "delay_min = 0" in text and "delay_min = 7" not in text

    window.settings.language.set_value("en")
    assert window.title.text() == "Wallets" and "Arbitrum RPC responds" in window.log.toPlainText()


def test_language_is_remembered_and_english_is_the_default(app, tmp_path):
    chain = FakeChain(time.monotonic)
    window, controller = start(tmp_path, chain)
    assert i18n.language() == "en" and window.title.text() == "Wallets"  # settings from 1.1: no [ui] section
    window.settings.language.set_value("ru")
    second = MainWindow()
    Controller(second, tmp_path / "settings.txt", tmp_path / "wallets.txt", chain_factory=lambda n, u: chain).load()
    assert i18n.language() == "ru" and second.title.text() == "Кошельки"


def test_theme_switch_repaints_the_log_and_is_saved(app, tmp_path):
    chain = FakeChain(time.monotonic, native=10**18)
    window, controller = start(tmp_path, chain)
    apply(app, controller)
    assert theme.is_dark() and theme.DARK.TEXT.lower() in window.log.toHtml().lower()
    window.settings.theme_button.click()
    assert theme.current().name == "light"
    html = window.log.toHtml()
    assert theme.LIGHT.TEXT.lower() in html.lower() and theme.DARK.TEXT.lower() not in html.lower()
    assert "theme = light" in (tmp_path / "settings.txt").read_text(encoding="utf-8")
    assert window.start_button.isEnabled() is False  # nothing checked; the switch itself changes nothing
    assert not controller.dirty


def test_failed_balances_are_polled_again_without_touching_the_rest(app, tmp_path):
    chain = FakeChain(time.monotonic, native=10**18)
    failing = Account.from_key(KEYS[1]).address
    chain.fail_for.add(failing)
    window, controller = start(tmp_path, chain, broken=False)
    controller.poll_options = {"sleep": lambda s: None}
    apply(app, controller)
    model = window.model
    assert model.failed_rows() == [1] and window.retry_button.isVisibleTo(window)
    assert window.retry_button.text() == "Retry failed (1)" and model.retry_enabled
    assert "#2 W2: balance check failed" in window.log.toPlainText()  # the reason is in the log (spec 5.2)
    totals = model.totals()
    assert totals.wallets == 2 and totals.failed == (2,)

    model.toggle(0)
    chain.fail_for.clear()
    controller.retry(model.failed_rows())
    wait_until(app, lambda: not controller.retrying and not model.rows[1].native.loading)
    app.processEvents()
    assert model.failed_rows() == [] and model.rows[1].native.value == 1
    assert model.rows[0].checked and not model.rows[2].checked  # the checkboxes stayed as they were
    assert model.totals().wallets == 3 and not window.retry_button.isVisibleTo(window)
    assert "Retry: loaded the balances of 1 wallet" in window.log.toPlainText()
    assert window.start_button.isEnabled()


def test_rate_limited_rpc_slows_down_with_one_log_line(app, tmp_path):
    clock = FakeClock()
    chain = FakeChain(clock, native=10**18)
    chain.rate_limit = (2, 1.0)
    window, controller = start(tmp_path, chain, broken=False)
    controller.poll_options = {"sleep": clock.sleep, "clock": clock}
    apply(app, controller)
    log = window.log.toPlainText()
    assert log.count("RPC is rate limiting requests") == 1 and chain.limited > 0
    assert window.model.failed_rows() == [] and window.model.totals().wallets == 3


def test_bridged_token_on_avalanche_warns_before_the_start(app, tmp_path, monkeypatch):
    """Avalanche and USDC.e: Apply checks chain ID 43114, the confirmation window warns about the bridged token,
    and the transaction link leads to snowtrace.io (spec 13.4, 13.5)."""
    usdc_e = "0xA7D7079b0FEaD91F3e65f86E8915Cb59c1a4C664"
    chain = FakeChain(time.monotonic, native=10**18, token=5_000_000, token_address=usdc_e, mine_after=0,
                      chain_id=43114)
    chain.symbol = "USDC.e"
    window, controller = start(tmp_path, chain, broken=False,
                               settings=SETTINGS.replace("arbitrum", "avalanche").replace("native", "usdc.e"))
    apply(app, controller)
    assert controller.applied is not None and controller.applied.token.label == "USDC.e"
    assert "Avalanche RPC responds, chain ID 43114" in window.log.toPlainText()
    assert window.model.rows[0].token.value == 5 and window.model.native_label == "AVAX"
    window.model.toggle(0)

    warnings: list[str] = []
    monkeypatch.setattr(ConfirmDialog, "exec", lambda self: (warnings.extend(
        label.text() for label in self.findChildren(type(window.counter)) if label.objectName() == "Warning"),
        QDialog.DialogCode.Accepted)[1])
    controller.start()
    wait_until(app, lambda: not controller.running)
    assert len(warnings) == 1 and warnings[0].startswith("USDC.e is a bridged version of USDC.")
    assert window.model.rows[0].tx_url.startswith("https://snowtrace.io/tx/")
