#!/bin/sh
# Rendered from thehub-pr/federation-templates/PRII-APP.sh — do not hand-edit.
# Launcher (Linux). Double-click where your file manager allows executing
# scripts, or run ./PRII-SPIDERWEB.sh. Finds a Python and hands over to
# desktop/setup.py, which sets the app up on first run and starts it.
# Options are passed through: run with --help to see them.
set -eu
cd "$(dirname "$0")"

# Newest Python first; every candidate is checked against the 3.10 floor.
PYTHON=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 \
    && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' 2>/dev/null; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "Python 3.10 or newer is required (for example: sudo apt install python3 python3-venv)."
  echo "Se requiere Python 3.10 o posterior (por ejemplo: sudo apt install python3 python3-venv)."
  if [ -t 0 ]; then
    printf '%s' "Press Enter to close / Presione Intro para cerrar… "
    read -r _
  fi
  exit 1
fi

exec "$PYTHON" desktop/setup.py --launch "$@"
