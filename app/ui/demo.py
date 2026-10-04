"""Demo data for reviewing the design: no keys and no network access.

The texts are the program's own messages, so the demo switches languages like the program does."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from PySide6.QtWidgets import QApplication

from app import i18n
from app.i18n import t
from app.networks import NETWORKS
from app.text import short_address
from app.ui import theme
from app.ui.confirm_dialog import RunSummary
from app.ui.main_window import MainWindow
from app.ui.wallet_table import Balance, Mark, State, WalletRow

ADDRESSES = [
    "0xF821946C16eADeac41E516E1330CD7d03316d92D",
    "0x4Ce896d765DF9EbE842ABAaa45Ff8CAAf4193D7E",
    "0x29fab7e383d417Bc3A2170d64793F81e749A66Fc",
    "0x6f2832eEE9443949f960C7773bF9D6dbB950a1f1",
    "0x81e4752DcA5dAaD1ef80B8ec18B97e3E8Fa2BAC0",
    "0xB1d4a07AA6Ca58Ead0f335e5BBc49b6ecd59ADee",
    "0xba5e0Cf2cfcbF0860E1e9c0E2d707c734E717E2D",
    "0x04902eF98cE23D821FF6EB03CDC9573019b6033E",
    "0x1B0C45A679014A8D26a20899c617Be54a9c85BCD",
    "0x20Bc4345447448f8E6875d44828AedA6d58270a8",
    "0xC5FA03776804B34AD437622Ef9c8C514400D4cED",
    "0xd53f95Bb560074a483861761be32eB3425852FA7",
    "0x48077D7589cC05526463333248182346CfA98047",
    "0x90264a52BF5dB9ce32d0378FfD08795d57a15D16",
    "0x2E0Cd8C139d28f235ba64F38027aE2350c9c2BCe",
    "0xB5693936173a30C13C8a0e9d7e420Dac13921CD9",
    "0x14d7a5Ab0bB06aBB54FCbEF4ca833884a0390C69",
    "0x805BACBeb75c0026026ea63810e2318b2790d3E4",
    "0xee11938c3682d595ae79c2D7Bc9cF3bfc537A0E3",
    "0xacbeC52ded136BA5828CB7101C9A8eE03B99D393",
    "0xeABBBEe4E5A772A9168bf513aD6f69Fa08F87cb8",
    "0x9E713363DCa3D77bf64c7Ff825053dfE5048503F",
    "0xD7387935494cFD3ba00c53328d39e116401BC04E",
    "0x55eB1f7AA3767089Df35568c2C186966c1bAF0b2",
]

TX_HASHES = [
    "0x49418f752c02cb23dfe57ecc6df8c5159f3bff5c08ad0caab388c6e077a16bf5",
    "0xb6d07fe13f3ee581f69a074a7ad4dbf89b6eb94c0bdf2c92667f39e16ba42e9a",
    "0x772e65e3b80e89ea10441a4c8844d4ee7bfea6cc34e5b7ced661bac66b584a9c",
    "0xb9246eb9b6bcdab7526a792d6c0c9d5eb20f1b44b03745e1bb4ea2d8e1a7a56f",
    "0xcd530fe7eaa5c693d680b3594f89773af259b6d31125c51e8c356b0edec03ce7",
]

NETWORK = NETWORKS["base"]
TOKEN = NETWORK.preset("usdc")

# Name, USDC balance, ETH balance. None — a line with an error in wallets.txt; "error" — the balance check failed.
# Wallet names are user data: one is in Cyrillic, as it may be in wallets.txt
WALLETS = [
    ("Main 1", "120.5", "0.0021"),
    ("", "0", "0.0008"),
    ("Bybit", "48.2", "0.0015"),
    ("Farm 07", "15.75", "0.00003"),
    ("Farm 08", "22.1", "0.0019"),
    ("Farm 09", "error", "error"),
    ("Резерв", "64.9", "0.0024"),
    ("Farm 10", "12.33", "0.0011"),
    ("Farm 11", "18", "0.0012"),
    ("Test", None, None),
    ("Farm 12", "9.8", "0.0009"),
    ("Farm 13", "27.64", "0.0013"),
]


def _rows() -> list[WalletRow]:
    rows = []
    for i, (name, token, native) in enumerate(WALLETS):
        sender, recipient = ADDRESSES[2 * i], ADDRESSES[2 * i + 1]
        if token is None:
            rows.append(WalletRow(i + 1, name, None, recipient, line_error=t("invalid private key")))
        elif token == "error":
            error = t("the RPC limits the request rate ({detail})", detail="429")
            rows.append(WalletRow(i + 1, name, sender, recipient, token=Balance(error=error),
                                  native=Balance(error=error)))
        else:
            rows.append(WalletRow(i + 1, name, sender, recipient,
                                  token=Balance(Decimal(token)), native=Balance(Decimal(native))))
    return rows


def _at(hour: int, minute: int, second: int) -> datetime:
    return datetime(2026, 10, 1, hour, minute, second)


def _wallet(num: int) -> i18n.Text:
    name = WALLETS[num - 1][0] or short_address(ADDRESSES[2 * (num - 1)])
    return t("#{num} {name}", num=num, name=name)


def _line(num: int, text) -> i18n.Text:
    return t("{prefix}: {text}", prefix=_wallet(num), text=text)


def _configure(window: MainWindow) -> None:
    settings = window.settings
    settings.network.setCurrentIndex(settings.network.findData(NETWORK.key))
    settings.token.setCurrentIndex(settings.token.findData(TOKEN.key))
    settings.amount_mode.set_value("range")
    settings.range_min.setValue(10)
    settings.range_max.setValue(15)
    settings.order.set_value("random")
    settings.set_token_info(t("Contract verified: {token}, {decimals} decimals", token=TOKEN.label,
                              decimals=TOKEN.decimals))
    settings.set_attention(None)
    window.set_file_summary(len(WALLETS), 1)
    window.show_token(TOKEN.label, TOKEN.address)
    window.log.network = NETWORK


def ready(window: MainWindow) -> None:
    """Settings applied, balances loaded, some wallets checked, one balance failed to load."""
    _configure(window)
    rows = _rows()
    for row in rows:
        row.checked = row.valid and not row.balance_failed and row.num not in (2, 11)
    window.model.set_rows(rows)
    window.set_retry_allowed(True)
    for when, text, level in (
        (_at(12, 0, 2), t("Settings saved to {file}", file="settings.txt"), "muted"),
        (_at(12, 0, 2), t("{file}, line {line}: {error}", file="wallets.txt", line=10, error=t("invalid private key")),
         "warn"),
        (_at(12, 0, 3), t("{network} RPC responds, chain ID {chain_id}", network=NETWORK.title,
                          chain_id=NETWORK.chain_id), "info"),
        (_at(12, 0, 3), t("Token {token}: {address}, {decimals} decimals", token=TOKEN.label, address=TOKEN.address,
                          decimals=TOKEN.decimals), "info"),
        (_at(12, 0, 4), t("{network} RPC is rate limiting requests — slowing down", network=NETWORK.title), "warn"),
        (_at(12, 0, 9), t("{prefix}: balance check failed — {error}", prefix=_wallet(6),
                          error=t("the RPC limits the request rate ({detail})", detail="429")), "warn"),
        (_at(12, 0, 9), t("Balances loaded: {count:wallets}; failed for {failed} — “Retry failed” polls them again",
                          count=10, failed=1), "warn"),
    ):
        window.log.add(text, level, when)


def running(window: MainWindow) -> None:
    """The mailing is in progress: every status and the attempt dots are visible."""
    _configure(window)
    rows = _rows()
    by_num = {row.num: row for row in rows}
    by_num[6].token, by_num[6].native = Balance(Decimal("31.4")), Balance(Decimal("0.0017"))
    for num in (1, 2, 3, 4, 5, 6, 7, 8, 9, 12):
        by_num[num].checked = True

    def status(num: int, state: State, text, marks: list[Mark], tx: int | None = None) -> None:
        row = by_num[num]
        row.state, row.status, row.marks = state, text, marks
        if tx is not None:
            row.tx_hash = TX_HASHES[tx]
            row.tx_url = NETWORK.tx_url(row.tx_hash)

    status(1, State.OK, t("Success: {amount}", amount="12.4817 USDC"), [Mark.OK], 0)
    status(2, State.SKIPPED, t("Skipped: {reason}", reason=t("zero balance")), [])
    status(3, State.OK, t("Success: {amount}", amount="14.0362 USDC"), [Mark.RETRY, Mark.OK], 1)
    status(4, State.SKIPPED, t("Skipped: {reason}", reason=t("low {symbol} for gas", symbol="ETH")), [])
    status(5, State.UNCONFIRMED, t("Not confirmed"), [Mark.RETRY, Mark.RETRY, Mark.RETRY, Mark.WARN], 2)
    status(6, State.CHECK, t("Needs review"), [Mark.WARN], 3)
    status(7, State.SENDING, t("Waiting for confirmation"), [Mark.RETRY, Mark.ACTIVE], 4)
    status(8, State.QUEUED, t("Queued"), [])
    status(9, State.ERROR, t("Error: {reason}", reason=t("RPC not responding")),
           [Mark.RETRY, Mark.RETRY, Mark.RETRY, Mark.FAIL])
    status(12, State.QUEUED, t("Queued"), [])
    by_num[1].token = Balance(Decimal("108.0183"))
    by_num[3].token = Balance(Decimal("34.1638"))

    window.model.set_rows(rows)
    window.set_running(True)
    window.band.set_progress(7 / 10)
    window.set_run_status(t("Processed {done} of {total}, now {wallet}", done=7, total=10, wallet=_wallet(7)))

    def sending(num: int, amount: str, attempt: int, *, replacement: bool = False):
        return t("{action} {amount} {token} → {to}, gas {gwei} gwei, attempt {attempt}/{total}",
                 action=t("replacement with the same nonce") if replacement else t("sending"), amount=amount,
                 token="USDC", to=short_address(ADDRESSES[2 * num - 1]), gwei="0.012", attempt=attempt, total=4)

    for when, text, level in (
        (_at(12, 0, 41), t("Sending started: {network}, {token}, {count:wallets}, {order}", network=NETWORK.title,
                           token="USDC", count=10, order=t("random order")), "info"),
        (_at(12, 0, 42), _line(1, sending(1, "12.4817", 1)), "info"),
        (_at(12, 0, 44), _line(1, t("success, block {block}, tx {tx}", block=36120544, tx=TX_HASHES[0])), "ok"),
        (_at(12, 0, 44), t("Delay {seconds} s", seconds=47), "muted"),
        (_at(12, 1, 31), _line(2, t("skipped: {detail}", detail=t("The wallet has 0 {token}", token="USDC"))), "muted"),
        (_at(12, 1, 32), _line(3, sending(3, "14.0362", 1)), "info"),
        (_at(12, 3, 32), _line(3, t("{reason}; retry in {seconds} s (attempt {attempt}/{total})",
                                    reason=t("did not get into a block in {seconds} s", seconds=120), seconds=10,
                                    attempt=1, total=4)), "warn"),
        (_at(12, 3, 43), _line(3, sending(3, "14.0362", 2, replacement=True)), "info"),
        (_at(12, 3, 45), _line(3, t("success, block {block}, tx {tx}", block=36120661, tx=TX_HASHES[1])), "ok"),
        (_at(12, 3, 45), t("Delay {seconds} s", seconds=62), "muted"),
        (_at(12, 4, 47), _line(4, t("skipped: {detail}", detail=t("Not enough {symbol} for gas: have {have}, need "
                                                                 "~{need}", symbol="ETH", have="0.00003",
                                                                 need="0.00006"))), "muted"),
        (_at(12, 4, 48), _line(9, t("{reason}; retry in {seconds} s (attempt {attempt}/{total})",
                                    reason=t("RPC error: {error}", error=t("no connection to the RPC")), seconds=10,
                                    attempt=1, total=4)), "warn"),
        (_at(12, 5, 20), _line(9, t("error after {count} attempts: {reason}", count=4,
                                    reason=t("RPC error: {error}", error=t("no connection to the RPC")))), "error"),
        (_at(12, 5, 20), t("Delay {seconds} s", seconds=38), "muted"),
        (_at(12, 14, 40), _line(5, t("not confirmed in {count} attempts, tx {tx} may still go through later", count=4,
                                     tx=TX_HASHES[2])), "warn"),
        (_at(12, 15, 36), _line(6, t("{detail}; block {block}, tx {tx}. Needs review",
                                     detail=t("The transaction went through, but the Transfer event to the recipient "
                                              "was not found"), block=36120802, tx=TX_HASHES[3])), "warn"),
        (_at(12, 16, 47), _line(7, sending(7, "13.5520", 1)), "info"),
        (_at(12, 18, 58), _line(7, t("tx {tx} sent", tx=TX_HASHES[4])), "info"),
    ):
        window.log.add(text, level, when)


def custom_token(window: MainWindow) -> None:
    """Another look of the panel: BSC, a token by address, a percent of the balance, the RPC section open."""
    settings = window.settings
    settings.network.setCurrentIndex(settings.network.findData("bsc"))
    settings.token.setCurrentIndex(settings.token.findData("custom"))
    settings.token_address.setText("0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82")
    settings.token_address.setCursorPosition(0)
    settings.amount_mode.set_value("percent")
    settings.percent.setValue(50)
    settings.rpc_section.set_open(True)
    settings.set_attention(t("Settings changed. Click Apply to save them, check the RPC and refresh balances."))


def summary() -> RunSummary:
    return RunSummary(
        network=NETWORK,
        token=TOKEN.label,
        token_address=TOKEN.address,
        amount=t("random from {low} to {high} {token}", low="10", high="15", token="USDC"),
        wallets=9,
        gas_multiplier="1.2",
        delay=t("from {low} to {high} sec", low=30, high=90),
        order=t("Random"),
        balances=i18n.tr("{token} and {native}", token="339.22 USDC", native="0.0138 ETH"),
    )


def bridged_summary() -> RunSummary:
    """The confirmation window for a bridged token: it warns that exchanges often credit only the native one."""
    network = NETWORKS["avalanche"]
    token = network.preset("usdc.e")
    return RunSummary(
        network=network,
        token=token.label,
        token_address=token.address,
        amount=t("whole {token} balance", token=token.label),
        wallets=9,
        gas_multiplier="1.2",
        delay=t("from {low} to {high} sec", low=30, high=90),
        order=t("Random"),
        balances=i18n.tr("{token} and {native}", token="412.06 USDC.e", native="1.8350 AVAX"),
        bridged_of=token.bridged_of,
    )


def connect_view(window: MainWindow) -> None:
    """In the demo the language and theme switches work too, without saving anything."""

    def language(code: str) -> None:
        i18n.set_language(code)
        window.retranslate()

    def toggle_theme() -> None:
        theme.apply_theme(QApplication.instance(), "light" if theme.is_dark() else "dark")
        window.restyle()

    window.settings.language_requested.connect(language)
    window.settings.theme_requested.connect(toggle_theme)
