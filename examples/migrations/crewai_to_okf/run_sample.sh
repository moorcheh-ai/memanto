#!/usr/bin/env bash
set -e

echo "=== CrewAI → Memanto OKF Migration Showcase ==="
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
OUTPUT_DIR="$SCRIPT_DIR/sample_output/okf"

rm -rf "$OUTPUT_DIR"

python3 "$SCRIPT_DIR/migrate_crewai.py" \
  --source "$SCRIPT_DIR/sample_data.json" \
  --output "$OUTPUT_DIR"

echo ""
echo "=== Migration Complete ==="
echo "Exported OKF files in $OUTPUT_DIR:"
ls -l "$OUTPUT_DIR"
