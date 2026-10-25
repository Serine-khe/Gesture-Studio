#!/usr/bin/env bash
# Gesture Studio - one-time setup for macOS and Linux.
set -e
cd "$(dirname "$0")"

echo "================================================"
echo "  Gesture Studio - one-time setup (macOS / Linux)"
echo "================================================"

# Find a Python version that MediaPipe supports (3.9 - 3.12), preferring 3.11.
PY=""
for v in 3.11 3.12 3.10 3.9; do
  if command -v "python$v" >/dev/null 2>&1; then PY="python$v"; break; fi
done
if [ -z "$PY" ] && command -v python3 >/dev/null 2>&1; then
  if python3 -c 'import sys; sys.exit(0 if (3,9) <= sys.version_info[:2] <= (3,12) else 1)'; then
    PY="python3"
  fi
fi
if [ -z "$PY" ]; then
  echo "[!] Could not find Python 3.9 - 3.12."
  echo "    macOS:  brew install python@3.11   (or download from https://www.python.org/downloads/)"
  echo "    Ubuntu: sudo apt install python3.11 python3.11-venv"
  exit 1
fi
echo "Using Python: $PY ($($PY --version))"

if [ ! -x ".venv/bin/python" ]; then
  echo "Creating virtual environment in .venv ..."
  "$PY" -m venv .venv
fi

echo "Installing packages (this can take a few minutes the first time) ..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo "Checking camera and speakers ..."
.venv/bin/python run.py --check || true
echo
echo "Setup finished! Start Gesture Studio with:  ./run_mac_linux.sh"
