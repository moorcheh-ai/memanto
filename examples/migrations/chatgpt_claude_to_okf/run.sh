#!/usr/bin/env bash
# One-command reproducibility: sample -> bundle -> tests -> validation report.
set -euo pipefail
cd "$(dirname "$0")"

echo "== [1/5] Generate realistic sample export =="
python3 generate_sample.py --out sample_data/chatgpt_export

echo "== [2/5] Convert ChatGPT export -> OKF bundle =="
python3 convert.py chatgpt sample_data/chatgpt_export --out okf_bundle

echo "== [3/5] Run tests =="
python3 -m pytest tests/ -q

echo "== [4/5] Round-trip validation (offline recall parity) =="
python3 validate_roundtrip.py chatgpt sample_data/chatgpt_export okf_bundle

echo "== [5/5] Memanto CLI dry-run (requires MOORCHEH_API_KEY) =="
if [ -n "${MOORCHEH_API_KEY:-}" ]; then
  memanto migrate okf ./okf_bundle --dry-run
else
  echo "skipped — set MOORCHEH_API_KEY to validate against the real Memanto import"
fi

echo
echo "Done. Bundle: $(pwd)/okf_bundle"
