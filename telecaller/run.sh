#!/usr/bin/env bash
# One-command start: creates the venv on first run, installs the two dependencies,
# runs the regression tests, then serves the console on :8000.
set -euo pipefail
cd "$(dirname "$0")/backend"

PY=${PYTHON:-python3}
if [ ! -d ../.venv ]; then
  echo "→ creating virtualenv"
  "$PY" -m venv ../.venv
fi
# shellcheck disable=SC1091
source ../.venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "→ running engine tests"
python test_engine.py

echo "→ http://localhost:${PORT:-8000}/app"
exec python -m uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}"
