#!/usr/bin/env bash
# Single-command ChatGPT → Memanto → OKF freedom-loop demo (offline-capable).
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Generating ChatGPT-shaped sample export"
python3 scripts/generate_sample_export.py

echo "==> Mapping + writing migration report + OKF sample"
python3 scripts/map_and_report.py

echo
echo "Done. Inspect:"
echo "  reports/migration_summary.md"
echo "  okf_sample/index.md"
echo "  MAPPING.md"
echo
echo "Live path (requires Memanto + MOORCHEH_API_KEY):"
echo "  memanto migrate chatgpt --file ./data/conversations.json --dry-run --report"
echo "  memanto memory export --okf ./okf_live"
