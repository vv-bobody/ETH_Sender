"""Where the program's files live: next to the .exe, or in the project root when run from sources."""
from __future__ import annotations

import sys
from pathlib import Path

if getattr(sys, "frozen", False):  # built with PyInstaller
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

SETTINGS_PATH = BASE_DIR / "settings.txt"
WALLETS_PATH = BASE_DIR / "wallets.txt"
