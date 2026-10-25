#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/python" ]; then
  echo "The app is not set up yet. Run ./setup_mac_linux.sh first."
  exit 1
fi
exec .venv/bin/python run.py "$@"
