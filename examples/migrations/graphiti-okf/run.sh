#!/usr/bin/env bash
# Offline freedom loop: seed → export → adapt → validate ($0)
set -euo pipefail
cd "$(dirname "$0")"
MODE="${1:-offline}"

echo "== graphiti-okf dry-run (mode=$MODE) =="
python3 seed_graphiti.py --mode "$MODE"
python3 export_graphiti.py --mode "$MODE"
python3 adapter.py
python3 validate_roundtrip.py --mode offline

echo
echo "OKF bundle: $(pwd)/out/okf-bundle"
echo "Summary:    $(pwd)/out/migration_summary.json"
echo "Validate:   $(pwd)/out/validation_report.md"
echo
echo "Optional (needs MOORCHEH_API_KEY + memanto CLI):"
echo "  memanto migrate okf ./out/okf-bundle --dry-run"
