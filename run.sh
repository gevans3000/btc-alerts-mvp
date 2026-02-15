#!/bin/bash
set -euo pipefail

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate

REQ_HASH_FILE=".venv/.requirements.sha256"
NEW_HASH=$(sha256sum requirements.txt | awk '{print $1}')
OLD_HASH=""
if [ -f "$REQ_HASH_FILE" ]; then
  OLD_HASH=$(cat "$REQ_HASH_FILE")
fi

if [ "${1:-}" = "--install" ] || [ "$NEW_HASH" != "$OLD_HASH" ]; then
  pip install -r requirements.txt
  echo "$NEW_HASH" > "$REQ_HASH_FILE"
fi

python app.py "$@"
