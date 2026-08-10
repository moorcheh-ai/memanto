#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SOURCE=${1:-"$ROOT/sample_data/codex-rollout-sanitized.jsonl"}
OUTPUT=${2:-"$ROOT/sample_output/okf-bundle"}
REEXPORTED="$ROOT/sample_output/reexported-okf"
PORTABILITY_REPORT="$ROOT/sample_output/portability-parity.json"

python "$ROOT/codex_to_okf.py" "$SOURCE" "$OUTPUT" \
  --title "A real Codex task: from changing context to portable memory"
python "$ROOT/validate_roundtrip.py" "$OUTPUT" \
  --golden "$ROOT/golden_qa.json" \
  --report "$ROOT/sample_output/recall-parity.json"

python "$ROOT/validate_portability.py" "$OUTPUT" "$REEXPORTED" \
  --report "$PORTABILITY_REPORT" \
  --replace
printf '%s\n' "  memanto migrate okf \"$OUTPUT\" --dry-run"
printf '%s\n' "Dry-run with Memanto:"
