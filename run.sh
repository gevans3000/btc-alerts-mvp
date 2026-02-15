#!/bin/bash
set -eo pipefail

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
# Use shasum -a 256 for macOS compatibility if sha256sum is missing
if command -v sha256sum >/dev/null 2>&1; then
  NEW_HASH=$(sha256sum requirements.txt | awk '{print $1}')
else
  NEW_HASH=$(shasum -a 256 requirements.txt | awk '{print $1}')
fi

OLD_HASH=""
if [ -f "$REQ_HASH_FILE" ]; then
  OLD_HASH=$(cat "$REQ_HASH_FILE")
fi

if [ "$INSTALL" -eq 1 ] || [ "$NEW_HASH" != "$OLD_HASH" ]; then
  echo "Installing requirements..."
  pip install -r requirements.txt
  echo "$NEW_HASH" > "$REQ_HASH_FILE"
fi

python3 app.py "${APP_ARGS[@]}"
