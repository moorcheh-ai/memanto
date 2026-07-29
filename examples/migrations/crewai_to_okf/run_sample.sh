#!/usr/bin/env bash
set -e

echo "=== CrewAI → Memanto OKF Migration Showcase ==="
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

python3 "$SCRIPT_DIR/migrate_crewai.py" \
  --source "$SCRIPT_DIR/sample_data.json" \
  --output "$SCRIPT_DIR/sample_output/okf"

echo ""
echo "=== Migration Complete ==="
echo "Exported OKF files in $SCRIPT_DIR/sample_output/okf:"
ls -l "$SCRIPT_DIR/sample_output/okf"
