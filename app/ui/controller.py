"""Connects the window with the logic: Apply, polling retries, Start, Stop, the language and the theme, and the
background threads (spec 5, 12)."""
from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from app import i18n
from app import settings as settings_file
from app import wallets as wallets_file
from app.apply import ApplyError, check_rpc, poll_balances, resolve_token
from app.chain import Chain
from app.i18n import Text, t, tr
from app.networks import NETWORKS, Network
from app.sender import Job, Mailing, Plan, Token, wallet_prefix
from app.settings import Settings
from app.totals import State as TotalState
from app.ui import theme
from app.ui.confirm_dialog import ConfirmDialog, RunSummary
from app.ui.main_window import MainWindow, sum_parts
from app.ui.wallet_table import Balance, Mark, State, WalletRow
from app.units import plain
from app.wallets import WalletEntry

HINT_START = t("Click Apply to check the RPC and load the balances.")
HINT_EDITED = t("Settings changed. Click Apply to save them, check the RPC and refresh balances.")
HINT_FAILED = t("Settings were not applied. Fix the error and click Apply again.")
STOPPING = t("Stopping after the current wallet…")


class _Bridge(QObject):
    """Signals from the background threads: Qt delivers them to the main thread, where the window lives."""

    row = Signal(int, object)
    log = Signal(object, str)
    progress = Signal(int, int, object)
    apply_done = Signal(object)
    retry_done = Signal(object)  # one retry batch is done: (rows, rows that failed again)
    retry_idle = Signal()  # the retry queue is empty
    run_done = Signal()


class _Events:
    """Events of the logic for the window — only through signals: they come from background threads."""

    def __init__(self, bridge: _Bridge) -> None:
        self.bridge = bridge

    def update(self, row: int, changes: dict) -> None:
        self.bridge.row.emit(row, changes)

    def log(self, text: Text | str, level: str = "info") -> None:
        self.bridge.log.emit(text, level)

    def progress(self, done: int, total: int, text: Text | str) -> None:
        self.bridge.progress.emit(done, total, text)


@dataclass
class _Applied:
    """What the last Apply checked: the mailing and the polling retries go with exactly this."""

    settings: Settings
    network: Network
    token: Token
    chain: Chain


def amount_text(settings: Settings, token: Token) -> Text:
    if settings.amount_mode == "all":
        if token.native:
            return t("whole {token} balance, except the amount for gas", token=token.label)
        return t("whole {token} balance", token=token.label)
    if settings.amount_mode == "percent":
        return t("{percent}% of the {token} balance", percent=plain(settings.percent), token=token.label)
    return t("random from {low} to {high} {token}", low=plain(settings.range_min), high=plain(settings.range_max),
             token=token.label)


class Controller(QObject):
    def __init__(self, window: MainWindow, settings_path: Path, wallets_path: Path,
                 chain_factory: Callable[[Network, str], Chain] = Chain) -> None:
        super().__init__(window)
        self.window = window
        self.settings_path = settings_path
        self.wallets_path = wallets_path
        self.chain_factory = chain_factory
        self.entries: list[WalletEntry] = []
        self._logged_errors: set[tuple[int, Text]] = set()
        self.applied: _Applied | None = None
        self.dirty = True
        self.polling = False  # balances are polled after Apply
        self.running = False
        self.stop_event = threading.Event()
        self._retry_lock = threading.Lock()
        self._retry_queue: list[int] = []
        self.retrying = False  # some wallets are polled again (spec 12.5)
        self.poll_options: dict = {}  # extra arguments of poll_balances: tests pass a clock that does not really wait

        self.bridge = _Bridge()
        self.events = _Events(self.bridge)
        self.bridge.row.connect(self._on_row)
        self.bridge.log.connect(self._on_log)
        self.bridge.progress.connect(self._on_progress)
        self.bridge.apply_done.connect(self._on_apply_done)
        self.bridge.retry_done.connect(self._on_retry_done)
        self.bridge.retry_idle.connect(self._on_retry_idle)
        self.bridge.run_done.connect(self._on_run_done)

        panel = window.settings
        panel.apply_requested.connect(self.apply)
        panel.edited.connect(self._on_edited)
        panel.language_requested.connect(self.set_language)
        panel.theme_requested.connect(self.toggle_theme)
        window.start_button.clicked.connect(self.start)
        window.stop_button.clicked.connect(self.stop)
        window.retry_button.clicked.connect(lambda: self.retry(window.model.failed_rows()))
        window.model.retry_requested.connect(self.retry)
        window.model.checked_changed.connect(self._update_start)
        window.close_guard = self._confirm_close

    # --- starting the program --------------------------------------------------------------------------

    def load(self) -> None:
        """Settings and wallets from the files; balances appear after Apply (spec 4.1)."""
        settings, warnings = settings_file.load(self.settings_path)
        self._show_view(settings.language, settings.theme)
        self.window.settings.set_settings(settings)
        for text in warnings:
            self._on_log(text, "warn")
        self._read_wallets()
        self._set_dirty(True, HINT_START)
        self._update_retry()

    def _read_wallets(self) -> None:
        entries, message = wallets_file.load(self.wallets_path)
        if message:
            self._on_log(message, "warn")
        self.entries = entries
        self.window.model.set_rows([
            WalletRow(entry.num, entry.name, entry.sender, entry.recipient, line_error=entry.error)
            for entry in entries
        ])
        invalid = [entry for entry in entries if not entry.valid]
        self.window.set_file_summary(len(entries), len(invalid))
        errors = {(entry.line_no, entry.error) for entry in invalid}
        for line_no, error in sorted(errors - self._logged_errors, key=lambda item: item[0]):  # no repeats
            self._on_log(t("{file}, line {line}: {error}", file=self.wallets_path.name, line=line_no, error=error),
                         "warn")
        self._logged_errors = errors

    # --- language and theme (spec 12.2, 12.3) ----------------------------------------------------------

    def _show_view(self, language: str, theme_name: str) -> None:
        i18n.set_language(language)
        theme.apply_theme(QApplication.instance(), theme_name)
        self.window.settings.set_language(language)
        self.window.retranslate()
        self.window.restyle()

    def set_language(self, code: str) -> None:
        """The RU | EN switch: everything on the screen in the other language at once; no Apply needed."""
        if code == i18n.language():
            return
        i18n.set_language(code)
        self.window.retranslate()
        self._save_view()

    def toggle_theme(self) -> None:
        theme.apply_theme(QApplication.instance(), "light" if theme.is_dark() else "dark")
        self.window.restyle()
        self._save_view()

    def _save_view(self) -> None:
        """Only the [ui] lines of settings.txt change: unsaved edits of the other fields stay out of the file."""
        try:
            settings_file.save_ui(self.settings_path, language=i18n.language(), theme=theme.current().name)
        except OSError as exc:
            self._on_log(t("Could not save the language and theme to {file}: {error}", file=self.settings_path.name,
                           error=str(exc)), "warn")

    # --- Apply (spec 5.1) ------------------------------------------------------------------------------

    def apply(self) -> None:
        if self.polling or self.running or self.retrying:
            return
        settings = self.window.settings.get_settings()
        errors = settings_file.validate(settings)
        if errors:
            self._message(tr("Check the settings"), "\n".join(str(error) for error in errors))
            return
        try:
            settings_file.save(self.settings_path, settings)
        except OSError as exc:
            self._message(tr("Settings were not saved"), tr("Could not write {file}: {error}",
                                                             file=self.settings_path.name, error=str(exc)))
            return
        self._on_log(t("Settings saved to {file}", file=self.settings_path.name), "muted")
        self._read_wallets()
        network = NETWORKS[settings.network]
        self.window.log.network = network
        self.applied = None
        self.polling = True
        self._set_dirty(False, None)
        self.window.settings.set_locked(True)
        self._update_retry()
        jobs = [(row, entry) for row, entry in enumerate(self.entries) if entry.valid]
        for row, _ in jobs:
            self._on_row(row, {"loading": True})
        self._on_progress(0, len(jobs), t("Checking balances: {done} / {total}", done=0, total=len(jobs)))
        chain = self.chain_factory(network, settings.rpc[settings.network])
        threading.Thread(target=self._apply_worker, args=(chain, network, settings, jobs), daemon=True).start()

    def _poll(self, chain: Chain, network: Network, token: Token, jobs: list[tuple[int, WalletEntry]],
              on_row: Callable[[int, dict], None] | None = None) -> int:
        """Polls balances with the progress in the status line and one log line about a rate limit (spec 12.5)."""
        total = len(jobs)
        done = [0]
        limited = threading.Event()

        def on_progress(count: int, _: int) -> None:
            done[0] = count
            self.events.progress(count, total, t("Checking balances: {done} / {total}", done=count, total=total))

        def on_limit(seconds: int) -> None:
            if not limited.is_set():
                limited.set()
                self.events.log(t("{network} RPC is rate limiting requests — slowing down", network=network.title),
                                "warn")
            self.events.progress(done[0], total, t("Checking balances: {done} / {total} — RPC rate limit, waiting "
                                                   "{seconds} s", done=done[0], total=total, seconds=seconds))

        return poll_balances(chain, token, jobs, on_row or self.events.update, on_progress, on_limit=on_limit,
                             **self.poll_options)

    def _apply_worker(self, chain: Chain, network: Network, settings: Settings,
                      jobs: list[tuple[int, WalletEntry]]) -> None:
        try:
            check_rpc(chain, network)
            self.events.log(t("{network} RPC responds, chain ID {chain_id}", network=network.title,
                              chain_id=network.chain_id))
            token = resolve_token(chain, network, settings.token)
            if not token.native:
                self.events.log(t("Token {token}: {address}, {decimals} decimals", token=token.label,
                                  address=token.address, decimals=token.decimals))
            failed = self._poll(chain, network, token, jobs)
            self.bridge.apply_done.emit((_Applied(settings, network, token, chain), len(jobs), failed, None))
        except ApplyError as exc:
            self.bridge.apply_done.emit((None, len(jobs), 0, exc.message))
        except Exception as exc:  # noqa: BLE001 — show it instead of failing silently
            self.bridge.apply_done.emit((None, len(jobs), 0, t("Unexpected error: {error}", error=str(exc))))

    def _on_apply_done(self, payload: tuple) -> None:
        applied, total, failed, error = payload
        self.polling = False
        self.window.settings.set_locked(False)
        self._on_progress(0, 0, None)
        if error:
            for row in self.window.model.rows:
                row.token, row.native = Balance(), Balance()
            self.window.model.refresh_all()
            self._on_log(error, "error")
            self._set_dirty(True, HINT_FAILED)
            self._update_retry()
            self._message(tr("Settings were not applied"), str(error))
            return
        self.applied = applied
        token = applied.token
        self.window.show_token(token.label, token.address)
        if token.address:
            self.window.settings.set_token_info(t("Contract verified: {token}, {decimals} decimals", token=token.label,
                                                  decimals=token.decimals))
        if failed:
            self._on_log(t("Balances loaded: {count:wallets}; failed for {failed} — “Retry failed” polls them again",
                           count=total - failed, failed=failed), "warn")
        else:
            self._on_log(t("Balances loaded: {count:wallets}", count=total), "ok")
        self._update_retry()
        self._update_start()

    def _on_edited(self) -> None:
        if self.polling or self.running:
            return
        self._set_dirty(True, HINT_EDITED)

    def _set_dirty(self, dirty: bool, hint: Text | None) -> None:
        """Settings changed after Apply — Start is unavailable until the next Apply (spec 5.1)."""
        self.dirty = dirty
        self.window.settings.set_attention(hint)
        self._update_start()

    def _update_start(self) -> None:
        checked = self.window.model.counts()[0]
        ready = (self.applied is not None and not self.dirty and not self.polling and not self.running
                 and not self.retrying)
        self.window.start_button.setEnabled(ready and checked > 0)

    def _update_retry(self) -> None:
        """The ↻ icons and "Retry failed" work when nothing else is polling or sending (spec 12.5)."""
        self.window.set_retry_allowed(self.applied is not None and not self.polling and not self.running)

    # --- polling retries (spec 12.5) -------------------------------------------------------------------

    def retry(self, rows: list[int]) -> None:
        """Polls the balances of the given wallets again — with the settings of the last Apply."""
        if self.applied is None or self.polling or self.running:
            return
        model = self.window.model
        rows = [row for row in rows if 0 <= row < len(model.rows) and model.rows[row].balance_failed]
        if not rows:
            return
        for row in rows:
            self._on_row(row, {"loading": True})
        with self._retry_lock:
            self._retry_queue.extend(rows)
            start = not self.retrying
            self.retrying = True
        self.window.settings.apply_button.setEnabled(False)
        self._update_start()
        if start:
            threading.Thread(target=self._retry_worker, args=(self.applied,), daemon=True).start()

    def _retry_worker(self, applied: _Applied) -> None:
        while True:
            with self._retry_lock:
                batch, self._retry_queue = self._retry_queue, []
                if not batch:
                    self.retrying = False
                    break
            failed: list[int] = []

            def on_row(row: int, changes: dict) -> None:
                if "balance_error" in changes:
                    failed.append(row)
                self.events.update(row, changes)

            try:
                self._poll(applied.chain, applied.network, applied.token,
                           [(row, self.entries[row]) for row in batch], on_row)
            except Exception as exc:  # noqa: BLE001 — the rows must not stay "loading" forever
                for row in batch:
                    on_row(row, {"balance_error": t("Unexpected error: {error}", error=str(exc))})
            self.bridge.retry_done.emit((batch, failed))
        self.bridge.retry_idle.emit()

    def _on_retry_done(self, payload: tuple) -> None:
        batch, failed = payload
        loaded = len(batch) - len(set(failed))
        if failed:
            numbers = ", ".join(f"#{self.entries[row].num}" for row in sorted(set(failed)))
            self._on_log(t("Retry: loaded the balances of {count:wallets}, failed again: {numbers}", count=loaded,
                           numbers=numbers), "warn")
        else:
            self._on_log(t("Retry: loaded the balances of {count:wallets}", count=loaded), "ok")

    def _on_retry_idle(self) -> None:
        if self.retrying:  # a new retry has started in the meantime
            return
        self._on_progress(0, 0, None)
        self.window.settings.apply_button.setEnabled(not self.polling and not self.running)
        self._update_start()
        self.window.update_retry_button()

    # --- the mailing (spec 5.5–5.9) --------------------------------------------------------------------

    def start(self) -> None:
        if self.applied is None or not self.window.start_button.isEnabled():
            return
        applied, model = self.applied, self.window.model
        jobs = [Job(row, entry) for row, entry in enumerate(self.entries) if entry.valid and model.rows[row].checked]
        if not jobs:
            return
        settings = applied.settings
        summary = RunSummary(
            network=applied.network,
            token=applied.token.label,
            token_address=applied.token.address,
            amount=amount_text(settings, applied.token),
            wallets=len(jobs),
            gas_multiplier=plain(settings.gas_multiplier),
            delay=t("from {low} to {high} sec", low=settings.delay_min, high=settings.delay_max),
            order=t("Random") if settings.order == "random" else t("File order"),
        )
        preset = applied.network.preset(settings.token)
        summary.bridged_of = preset.bridged_of if preset else None  # USDC.e, USDbC, USDT.e (spec 13.5)
        totals = model.totals(checked_only=True)
        if totals.state is TotalState.READY:
            parts = sum_parts(totals, applied.token.label, None if applied.token.native else applied.network.symbol)
            short = (tr("{token} and {native}", token=parts[0][0], native=parts[1][0]) if len(parts) == 2
                     else parts[0][0])  # "342.80 USDC and 0.0150 ETH" (spec 12.1)
            full = "\n".join(full for _, full in parts)
            if totals.failed:
                note = tr("{count:wallets} excluded: balance check failed", count=len(totals.failed))
                short, full = f"{short}, {note}", f"{full}\n{note}"
            summary.balances, summary.balances_tooltip = short, full
        dialog = ConfirmDialog(summary, self.window)
        theme.style_titlebar(dialog)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.running = True
        self.stop_event.clear()
        self.window.set_running(True)
        self._update_start()
        self._update_retry()
        queued = {job.row for job in jobs}
        for row, entry in enumerate(self.entries):
            if entry.valid:
                self._on_row(row, {"state": "queued" if row in queued else "idle",
                                   "status": t("Queued") if row in queued else "—",
                                   "detail": None, "marks": [], "tx_hash": None})
        plan = Plan(settings.amount_mode, settings.percent, settings.range_min, settings.range_max,
                    settings.gas_multiplier, settings.tx_timeout, settings.delay_min, settings.delay_max,
                    settings.order)
        mailing = Mailing(applied.chain, applied.network, applied.token, plan, jobs, self.events, self.stop_event)
        threading.Thread(target=self._run_worker, args=(mailing,), daemon=True).start()

    def _run_worker(self, mailing: Mailing) -> None:
        try:
            mailing.run()
        except Exception as exc:  # noqa: BLE001
            self.events.log(t("Sending was interrupted by an unexpected error: {error}", error=str(exc)), "error")
        self.bridge.run_done.emit()

    def _on_run_done(self) -> None:
        self.running = False
        self.window.set_running(False)
        self._on_progress(0, 0, None)
        self._update_start()
        self._update_retry()

    def stop(self) -> None:
        """Stop: the current wallet is finished, during a delay — stops at once (spec 5.8)."""
        if not self.running or self.stop_event.is_set():
            return
        self.stop_event.set()
        self.window.stop_button.setEnabled(False)
        self.window.set_run_status(STOPPING)
        self._on_log(t("Stop pressed: sending will stop after the current wallet"), "warn")

    def _confirm_close(self) -> bool:
        if not self.running:
            return True
        return self._ask(tr("Sending in progress"),
                         tr("Close the program? The current transaction may remain unconfirmed."),
                         tr("Close"), tr("Continue sending"))

    # --- window updates --------------------------------------------------------------------------------

    def _on_row(self, index: int, changes: dict) -> None:
        model = self.window.model
        if not 0 <= index < len(model.rows):
            return
        row = model.rows[index]
        if changes.get("loading"):
            row.token, row.native = Balance(loading=True), Balance(loading=True)
        if "balance_error" in changes:
            row.token = Balance(error=changes["balance_error"])
            row.native = Balance(error=changes["balance_error"])
            if not self.running and index < len(self.entries):  # the reason goes to the log (spec 5.2, 12.1)
                self._on_log(t("{prefix}: balance check failed — {error}", prefix=wallet_prefix(self.entries[index]),
                               error=changes["balance_error"]), "warn")
        if "token_balance" in changes:
            row.token = Balance(changes["token_balance"])
        if "native_balance" in changes:
            row.native = Balance(changes["native_balance"])
        if "state" in changes:
            row.state = State(changes["state"])
        if "status" in changes:
            row.status = changes["status"]
        if "detail" in changes:
            row.detail = changes["detail"]
        if "marks" in changes:
            row.marks = [Mark(mark) for mark in changes["marks"]]
        if "tx_hash" in changes:
            row.tx_hash = changes["tx_hash"]
            network = self.applied.network if self.applied else None
            row.tx_url = network.tx_url(row.tx_hash) if row.tx_hash and network else None
        model.refresh_row(index)

    def _on_log(self, text: Text | str, level: str) -> None:
        self.window.log.add(text, level)

    def _on_progress(self, done: int, total: int, text: Text | str | None) -> None:
        self.window.band.set_progress(done / total if total else None)
        if self.running and self.stop_event.is_set():
            text = STOPPING
        self.window.set_run_status(text or None)

    # --- message boxes ---------------------------------------------------------------------------------

    def _box(self, title: str, text: str) -> QMessageBox:
        box = QMessageBox(self.window)
        box.setWindowTitle(title)
        box.setText(text)
        theme.style_titlebar(box)
        return box

    def _message(self, title: str, text: str) -> None:
        box = self._box(title, text)
        box.setIcon(QMessageBox.Icon.Warning)
        box.addButton(tr("OK"), QMessageBox.ButtonRole.AcceptRole)
        box.exec()

    def _ask(self, title: str, text: str, yes: str, no: str) -> bool:
        box = self._box(title, text)
        box.setIcon(QMessageBox.Icon.Question)
        yes_button = box.addButton(yes, QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(box.addButton(no, QMessageBox.ButtonRole.RejectRole))
        box.exec()
        return box.clickedButton() is yes_button
