"""Builds icon.ico for the .exe from the icon the program draws (every size in one file)."""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.ui.icons import APP_ICON_SIZES, app_icon_pixmap  # noqa: E402


def png_bytes(size: int) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    app_icon_pixmap(size).save(buffer, "PNG")
    return bytes(buffer.data())


def write_ico(path: Path) -> None:
    """An ICO with compressed PNGs inside — Windows Vista and newer read it so."""
    images = [(size, png_bytes(size)) for size in APP_ICON_SIZES]
    offset = 6 + 16 * len(images)
    header = struct.pack("<HHH", 0, 1, len(images))
    entries, blobs = b"", b""
    for size, data in images:
        side = size if size < 256 else 0  # 0 in the header means 256
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        blobs += data
    path.write_bytes(header + entries + blobs)


if __name__ == "__main__":
    app = QApplication(sys.argv)  # noqa: F841 — painting needs an application object
    target = ROOT / "icon.ico"
    write_ico(target)
    print(target)
