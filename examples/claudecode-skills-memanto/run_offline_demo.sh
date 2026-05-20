#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STORE="${1:-$ROOT_DIR/demo/memory.json}"

rm -f "$STORE"

python "$ROOT_DIR/bridge.py" \
  --backend local \
  --store "$STORE" \
  after \
  --skill grill-with-docs \
  --task "review API pagination design" \
  --path docs/api-pagination.md \
  --transcript "$ROOT_DIR/demo/session-one-transcript.md"

echo

python "$ROOT_DIR/bridge.py" \
  --backend local \
  --store "$STORE" \
  before \
  --skill tdd \
  --task "add pagination tests" \
  --path tests/test_api.py
