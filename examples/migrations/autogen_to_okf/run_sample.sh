#!/usr/bin/env bash
set -e

echo "=== AutoGen → Memanto OKF Migration Showcase ==="
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

python3 "$SCRIPT_DIR/migrate_autogen.py" \
  --source "$SCRIPT_DIR/sample_data.json" \
  --output "$SCRIPT_DIR/sample_output/okf"

echo ""
echo "=== Migration Complete ==="
ls -l "$SCRIPT_DIR/sample_output/okf"
