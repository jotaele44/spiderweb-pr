#!/bin/bash
# Rendered from thehub-pr/federation-templates/PRII-APP.command — do not hand-edit.
# Double-click launcher (macOS). Finds a Python and hands over to
# desktop/setup.py, which sets the app up on first run and starts it.
# Options are passed through: run with --help to see them.
set -uo pipefail
cd "$(dirname "$0")" || exit 1

# python.org installs to /usr/local/bin and its framework folder; Homebrew to
# /opt/homebrew/bin on Apple silicon.
export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:$PATH"

# Newest Python first. A bare `python3` is often Apple's 3.9, which is too old.
find_python() {
  local candidate
  for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1 \
      && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' 2>/dev/null; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

opened=0
until PYTHON="$(find_python)"; do
  echo "Python 3.10 or newer is not installed on this Mac."
  echo "Python 3.10 o posterior no está instalado en este Mac."
  if [ "$opened" = 0 ]; then
    echo "Opening the Python download page — run the installer it offers."
    echo "Abriendo la página de descarga de Python — ejecute el instalador que ofrece."
    open "https://www.python.org/downloads/" 2>/dev/null || true
    opened=1
  fi
  [ -t 0 ] || exit 1
  read -r -p "Press Return when Python is installed / Presione Retorno cuando Python esté instalado… " _
  hash -r
done

exec "$PYTHON" desktop/setup.py --launch "$@"
