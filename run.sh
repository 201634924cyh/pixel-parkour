#!/usr/bin/env bash
# ============================================================
#  Pixel Parkour - Linux / macOS launcher
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "Python not found. Please install Python 3 and run:  pip install pygame-ce"
    exit 1
fi

# pygame-ce provides the `pygame` module. If missing, hint the user.
if ! "$PY" -c "import pygame" >/dev/null 2>&1; then
    echo "pygame module not found. Installing pygame-ce ..."
    "$PY" -m pip install --user pygame-ce
fi

exec "$PY" game.py "$@"
