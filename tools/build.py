"""Builds ETH Sender into an .exe, checks the build and makes a desktop shortcut (spec 7).

Run from build.bat in the separate clean environment .venv-build. Packages are installed strictly from
requirements.lock: exact versions, SHA-256 hashes, ready-made wheels only. If even one file differs from the
locked one, pip stops the build. The result: dist\\ETH_Sender\\ETH_Sender.exe.
settings.txt and wallets.txt from dist\\ETH_Sender are kept: PyInstaller deletes the folder when rebuilding.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "ETH_Sender"
EXE = DIST / "ETH_Sender.exe"
PYTHON = sys.executable
USER_FILES = ("settings.txt", "wallets.txt")
BACKUP = ROOT / ".build-backup"  # copies of the user's files during the build; they may contain keys
PIP_INSTALL = ("-m", "pip", "install", "--disable-pip-version-check", "-q",
               "--require-hashes", "--only-binary=:all:", "-r")


def step(text: str) -> None:
    print(f"\n== {text}", flush=True)


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def locked_versions() -> dict[str, str]:
    versions = {}
    for path in ("requirements.lock", "requirements-pip.lock"):
        for line in (ROOT / path).read_text(encoding="ascii").splitlines():
            match = re.match(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", line)
            if match:
                versions[canonical(match.group(1))] = match.group(2)
    return versions


def check_environment() -> None:
    """The build environment must have exactly the locked packages, of the same versions."""
    expected = locked_versions()
    installed = {canonical(d.metadata["Name"]): d.version for d in metadata.distributions()}
    extra = sorted(set(installed) - set(expected))
    wrong = sorted(f"{name} {installed[name]} (expected {version})" for name, version in expected.items()
                   if installed.get(name) != version)
    if extra or wrong:
        raise SystemExit(f"The build environment does not match the lock files. Extra: {extra or 'none'}; "
                         f"other versions or not installed: {wrong or 'none'}")
    print(f"Exactly {len(installed)} packages from the lock files are installed, the versions match")


def backup_user_files() -> list[str]:
    BACKUP.mkdir(exist_ok=True)
    for name in USER_FILES:
        if (DIST / name).exists():
            shutil.copy2(DIST / name, BACKUP / name)  # a fresh copy; an older one stays if the file is gone now
    return [name for name in USER_FILES if (BACKUP / name).exists()]


def restore_user_files(saved: list[str]) -> None:
    DIST.mkdir(parents=True, exist_ok=True)
    for name in saved:
        shutil.copy2(BACKUP / name, DIST / name)
    shutil.rmtree(BACKUP, ignore_errors=True)


def create_shortcut() -> Path:
    """The "ETH Sender" desktop shortcut. Paths go through environment variables: spaces and non-Latin letters
    do not get in the way."""
    script = (
        "$link = Join-Path ([Environment]::GetFolderPath('Desktop')) 'ETH Sender.lnk';"
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($link);"
        "$s.TargetPath = $env:ETH_SENDER_EXE; $s.WorkingDirectory = $env:ETH_SENDER_DIR;"
        "$s.IconLocation = $env:ETH_SENDER_EXE + ',0'; $s.Description = 'ETH Sender'; $s.Save();"
        "Write-Output $link"
    )
    env = {**os.environ, "ETH_SENDER_EXE": str(EXE), "ETH_SENDER_DIR": str(DIST)}
    result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                            env=env, check=True, capture_output=True, text=True)
    return Path(result.stdout.strip())


def main() -> int:
    if Path(sys.prefix).name != ".venv-build":
        print("The build only runs in the clean .venv-build environment — run build.bat")
        return 1

    step("Installing pip from requirements-pip.lock")
    run(PYTHON, *PIP_INSTALL, "requirements-pip.lock")

    step("Installing packages strictly from requirements.lock: versions, hashes, ready-made wheels only")
    run(PYTHON, *PIP_INSTALL, "requirements.lock")
    check_environment()

    step("Drawing the icon")
    run(PYTHON, "tools/make_icon.py")

    step("Building ETH_Sender.exe")
    saved = backup_user_files()
    try:
        run(PYTHON, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN", "--onedir", "--windowed",
            "--name", "ETH_Sender", "--icon", "icon.ico",
            "--collect-submodules", "eth_hash", "--collect-data", "eth_account",
            "main.py")
    finally:
        restore_user_files(saved)
    if saved:
        print("Your files are kept:", ", ".join(saved))

    step("Checking the build")
    check = subprocess.run([str(EXE), "--selfcheck"], cwd=DIST)
    log = DIST / "selfcheck.log"
    if check.returncode != 0:
        print(log.read_text(encoding="utf-8") if log.exists() else "selfcheck.log was not created")
        return 1
    log.unlink(missing_ok=True)
    print("Transaction signing and network access work in the build")

    step("Creating the desktop shortcut")
    print(create_shortcut())

    print(f"\nDone: {EXE}")
    print("The dist\\ETH_Sender folder can be moved anywhere, but then rebuild or fix the shortcut.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        print(f"\nThe build failed: a command exited with code {exc.returncode}")
        sys.exit(1)
