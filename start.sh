#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.12
    uv pip sync --python .venv/bin/python requirements.lock
  else
    python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements.lock
  fi
fi
exec .venv/bin/python server.py
