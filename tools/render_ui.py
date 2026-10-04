"""Interface snapshots with demo data — for reviewing the design, both themes (spec 12.3).

Run from the project root: .venv\\Scripts\\python tools\\render_ui.py
The pictures go to design/. No windows appear on the screen.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from app import i18n  # noqa: E402
from app.ui import demo  # noqa: E402
from app.ui.confirm_dialog import ConfirmDialog  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.theme import apply_theme  # noqa: E402

OUT_DIR = os.path.join(ROOT, "design")


def show(widget: QWidget) -> None:
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    widget.show()
    for _ in range(3):
        QApplication.processEvents()


def save(widget: QWidget, name: str) -> None:
    path = os.path.join(OUT_DIR, name)
    widget.grab().save(path)
    print(path)


def snapshot(widget: QWidget, name: str) -> None:
    show(widget)
    save(widget, name)
    widget.close()


def render(suffix: str) -> None:
    ready = MainWindow()
    demo.ready(ready)
    snapshot(ready, f"1-ready{suffix}.png")

    running = MainWindow()
    demo.running(running)
    snapshot(running, f"2-running{suffix}.png")

    snapshot(ConfirmDialog(demo.summary()), f"3-confirm{suffix}.png")
    snapshot(ConfirmDialog(demo.bridged_summary()), f"3-confirm-bridged{suffix}.png")

    # The whole settings panel: the window is taller than usual, so that the open RPC section fits
    variant = MainWindow()
    variant.resize(1600, 1480)
    demo.custom_token(variant)
    show(variant)
    save(variant.settings, f"4-settings-variant{suffix}.png")
    variant.close()

    # The open network list with the highlighted Base row: its dot must not fade (spec 13.2)
    lists = MainWindow()
    demo.ready(lists)
    show(lists)
    combo = lists.settings.network
    combo.showPopup()
    combo.view().setCurrentIndex(combo.model().index(combo.findData("base"), 0))
    for _ in range(3):
        QApplication.processEvents()
    save(combo.view().window(), f"7-network-list{suffix}.png")
    combo.hidePopup()
    lists.close()


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    app = QApplication(sys.argv)
    for theme_name, suffix in (("dark", ""), ("light", "-light")):
        apply_theme(app, theme_name)
        render(suffix)
    i18n.set_language(i18n.RU)
    apply_theme(app, "dark")
    ready = MainWindow()
    ready.settings.set_language(i18n.RU)
    demo.ready(ready)
    snapshot(ready, "1-ready-ru.png")


if __name__ == "__main__":
    main()
