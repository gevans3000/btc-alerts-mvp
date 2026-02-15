#!/bin/bash
set -euo pipefail

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate

INSTALL=0
APP_ARGS=()
for arg in "$@"; do
  if [ "$arg" = "--install" ]; then
    INSTALL=1
  else
    APP_ARGS+=("$arg")
  fi
done

REQ_HASH_FILE=".venv/.requirements.sha256"
NEW_HASH=$(sha256sum requirements.txt | awk '{print $1}')
OLD_HASH=""
if [ -f "$REQ_HASH_FILE" ]; then
  OLD_HASH=$(cat "$REQ_HASH_FILE")
fi

if [ "$INSTALL" -eq 1 ] || [ "$NEW_HASH" != "$OLD_HASH" ]; then
  pip install -r requirements.txt
  echo "$NEW_HASH" > "$REQ_HASH_FILE"
fi

python app.py "${APP_ARGS[@]}"
