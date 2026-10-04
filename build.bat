@echo off
rem ETH Sender: build ETH_Sender.exe and a desktop shortcut.
rem Uses a separate clean environment .venv-build and installs only the packages
rem pinned with SHA-256 hashes in requirements.lock. Details: tools\build.py
setlocal
cd /d "%~dp0"
if not exist ".venv-build\Scripts\python.exe" (
    python -m venv .venv-build || goto :error
)
set PYTHONIOENCODING=utf-8
".venv-build\Scripts\python.exe" tools\build.py || goto :error
if not defined NO_PAUSE pause
exit /b 0

:error
echo.
echo Build failed, see the messages above.
if not defined NO_PAUSE pause
exit /b 1
