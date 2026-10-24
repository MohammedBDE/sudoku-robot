#!/usr/bin/env bash
# Set up sudoku_robot on Linux -- the robot's Raspberry Pi (real hardware)
# or any Linux dev machine (simulation only).
#
#   scripts/setup.sh              create .venv if missing, install pinned requirements, verify
#   scripts/setup.sh --fresh      delete and recreate .venv first (a guaranteed-clean install)
#   scripts/setup.sh --hardware   also require the serial port + DejaVu font (use this on the Pi)
#
# Needs Python 3.13 (the version requirements.txt is pinned against).
# Override the interpreter with PYTHON=/path/to/python3.13 scripts/setup.sh
# Works from any folder: it always operates on the project root (.venv is created there).
set -euo pipefail

SCRIPT="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
cd "$(dirname "$0")/.."   # project root

FRESH=0
VERIFY_ARGS=()
for arg in "$@"; do
    case "$arg" in
        --fresh) FRESH=1 ;;
        --hardware) VERIFY_ARGS+=(--hardware) ;;
        -h|--help) sed -n '2,11p' "$SCRIPT"; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
    if command -v python3.13 >/dev/null 2>&1; then PYTHON=python3.13; else PYTHON=python3; fi
fi
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "ERROR: $PYTHON not found. Install Python 3.13 (e.g. sudo apt install python3 python3-venv)." >&2
    exit 1
fi
PY_VERSION="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if [ "$PY_VERSION" != "3.13" ]; then
    echo "WARNING: $PYTHON is Python $PY_VERSION; requirements.txt is pinned for 3.13." >&2
    echo "         Pinned wheels may not exist for $PY_VERSION. Set PYTHON=python3.13 to be safe." >&2
fi

if [ "$FRESH" -eq 1 ] && [ -d .venv ]; then
    echo "==> Removing existing .venv (--fresh)"
    rm -rf .venv
fi
if [ ! -x .venv/bin/python ]; then
    echo "==> Creating .venv with $PYTHON"
    if ! "$PYTHON" -m venv .venv; then
        echo "ERROR: could not create a venv. On Debian/Raspberry Pi OS: sudo apt install python3-venv" >&2
        exit 1
    fi
fi

echo "==> Installing pinned requirements"
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

if [ ! -f config/camera_config.json ]; then
    echo "==> No config/camera_config.json yet (only needed for --from-camera):"
    echo "    cp config/camera_config.example.json config/camera_config.json   # then put your iPhone's rtsp:// URL in it"
fi

echo "==> Verifying the environment"
set +e
.venv/bin/python scripts/verify_env.py "${VERIFY_ARGS[@]+"${VERIFY_ARGS[@]}"}"
STATUS=$?
set -e
if [ $STATUS -ne 0 ]; then
    echo
    echo "Setup finished, but verification FAILED -- see the FAIL lines above." >&2
    exit $STATUS
fi
echo
echo "Done. Activate with:  source .venv/bin/activate"
