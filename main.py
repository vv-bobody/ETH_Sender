"""ETH Sender entry point.

Command-line switches:
  --demo               a window with demo data to review the design: nothing is sent, no network access
  --selfcheck          checks the build without a window: the result goes to selfcheck.log next to the program
  --selfcheck-network  the same plus a chain ID request to every network over the default RPCs (HTTPS, certificates)
"""
from __future__ import annotations

import sys


def selfcheck(network_check: bool) -> int:
    """Checks that the build has everything needed to sign and send transactions."""
    import traceback

    from app.paths import BASE_DIR

    report = BASE_DIR / "selfcheck.log"
    try:
        from eth_account import Account

        from app.chain import Chain, Fees, transfer_data
        from app.networks import NETWORKS

        account = Account.create()
        tx = {"chainId": 8453, "nonce": 0, "to": account.address, "value": 1, "data": transfer_data(account.address, 1),
              "gas": 21000, **Fees(False, 10, 1).tx_fields()}
        Account.sign_transaction(tx, account.key)
        lines = ["transaction signing: OK"]
        for network in NETWORKS.values():
            chain = Chain(network, network.default_rpc)
            if network_check:
                chain_id = chain.chain_id()
                if chain_id != network.chain_id:
                    raise RuntimeError(f"{network.title}: chain ID {chain_id}, expected {network.chain_id}")
                lines.append(f"{network.title}: chain ID {chain_id} OK")
        report.write_text("\n".join(lines) + "\nOK\n", encoding="utf-8")
        return 0
    except Exception:  # noqa: BLE001
        report.write_text(traceback.format_exc(), encoding="utf-8")
        return 1


def main() -> int:
    if "--selfcheck" in sys.argv or "--selfcheck-network" in sys.argv:
        return selfcheck(network_check="--selfcheck-network" in sys.argv)

    from PySide6.QtWidgets import QApplication

    from app.ui.main_window import MainWindow
    from app.ui.theme import apply_theme, style_titlebar

    app = QApplication(sys.argv)
    app.setApplicationName("ETH Sender")
    apply_theme(app)
    window = MainWindow()
    app.setWindowIcon(window.windowIcon())
    if "--demo" in sys.argv:
        from app.ui import demo
        from app.ui.confirm_dialog import ConfirmDialog

        demo.ready(window)
        demo.connect_view(window)

        def confirm() -> None:
            dialog = ConfirmDialog(demo.summary(), window)
            style_titlebar(dialog)
            dialog.exec()

        window.start_button.clicked.connect(confirm)
    else:
        from app.paths import SETTINGS_PATH, WALLETS_PATH
        from app.ui.controller import Controller

        controller = Controller(window, SETTINGS_PATH, WALLETS_PATH)
        controller.load()
    style_titlebar(window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
