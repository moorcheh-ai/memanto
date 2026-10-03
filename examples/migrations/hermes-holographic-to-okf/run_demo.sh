#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_REPO="${HERMES_REPO:-}"
HERMES_PYTHON="${HERMES_PYTHON:-python}"
MEMANTO_REPO="${MEMANTO_REPO:-$(cd "$ROOT/../../.." 2>/dev/null && pwd || true)}"
SOURCE_DB="$ROOT/fixtures/memory_store.db"
SOURCE_REPORT="$ROOT/reports/source-generation.json"
EXPORT_REPORT="$ROOT/reports/export-summary.json"
FIDELITY_REPORT="$ROOT/reports/fidelity.json"
MIGRATION_REPORT="$ROOT/reports/migration-report.md"
BUNDLE="$ROOT/output/okf_bundle"
ROUNDTRIP="$ROOT/output/memanto_roundtrip"
FRESH_EXPORT="$ROOT/output/fresh_destination"

if [[ -z "$HERMES_REPO" ]]; then
  echo "ERROR: set HERMES_REPO to a Hermes checkout containing plugins/memory/holographic/store.py" >&2
  exit 2
fi

run_python() {
  if command -v uv >/dev/null 2>&1 && [[ -f "$MEMANTO_REPO/pyproject.toml" ]]; then
    (cd "$MEMANTO_REPO" && uv run python "$@")
  else
    python "$@"
  fi
}

run_memanto() {
  if command -v uv >/dev/null 2>&1 && [[ -f "$MEMANTO_REPO/pyproject.toml" ]]; then
    (cd "$MEMANTO_REPO" && uv run memanto "$@")
  elif command -v memanto >/dev/null 2>&1; then
    memanto "$@"
  else
    echo "ERROR: memanto CLI is not installed; install the repository first." >&2
    exit 2
  fi
}

validate_bundle() {
  local bundle="$1"
  local report="$2"
  local args=("$ROOT/validate.py" "$SOURCE_DB" "$bundle" --report "$report")
  if [[ -f "$MEMANTO_REPO/memanto/cli/migrate/okf_loader.py" ]]; then
    args+=(--memanto-repo "$MEMANTO_REPO")
  fi
  run_python "${args[@]}"
}

run_golden_recall() {
  local transcript="$1"
  : > "$transcript"
  local failures=0

  while IFS=$'\t' read -r probe_id query needles; do
    {
      echo "=== $probe_id ==="
      echo "QUERY: $query"
    } >> "$transcript"

    local output
    if ! output="$(run_memanto recall "$query" --limit 20 2>&1)"; then
      echo "$output" >> "$transcript"
      echo "FAIL: recall command failed for $probe_id" >&2
      failures=$((failures + 1))
      continue
    fi
    echo "$output" >> "$transcript"

    IFS='|' read -r -a expected <<< "$needles"
    for needle in "${expected[@]}"; do
      if ! grep -Fqi -- "$needle" <<< "$output"; then
        echo "MISSING EXPECTED TEXT: $needle" >> "$transcript"
        failures=$((failures + 1))
      fi
    done
    echo >> "$transcript"
  done < <(
    python - "$ROOT/golden_questions.json" <<'PY'
import json
import sys

for probe in json.load(open(sys.argv[1], encoding="utf-8")):
    print(
        probe["id"],
        probe["query"].replace("\t", " "),
        "|".join(probe["must_contain"]),
        sep="\t",
    )
PY
  )

  if (( failures > 0 )); then
    echo "Golden recall FAIL: $failures missing/failed checks; see $transcript" >&2
    return 1
  fi
  echo "Golden recall PASS: $transcript"
}

rm -rf "$BUNDLE" "$ROUNDTRIP" "$FRESH_EXPORT"
mkdir -p "$ROOT/fixtures" "$ROOT/output" "$ROOT/reports"

echo "[1/5] Generate a real Holo source through Hermes MemoryStore operations"
"$HERMES_PYTHON" "$ROOT/generate_demo_source.py" \
  --hermes-repo "$HERMES_REPO" \
  --output "$SOURCE_DB" \
  --report "$SOURCE_REPORT"

echo "[2/5] Export Holo SQLite -> portable OKF"
run_python "$ROOT/export_holo.py" "$SOURCE_DB" "$BUNDLE" --report "$EXPORT_REPORT"

echo "[3/5] Independent field-level fidelity validation"
validate_bundle "$BUNDLE" "$FIDELITY_REPORT"

echo "[4/5] Build Holo-specific migration/accounting report + run Memanto dry-run"
run_python "$ROOT/build_report.py" \
  --source-report "$SOURCE_REPORT" \
  --export-report "$EXPORT_REPORT" \
  --fidelity-report "$FIDELITY_REPORT" \
  --output "$MIGRATION_REPORT"
run_memanto migrate okf "$BUNDLE" --dry-run

echo "[5/5] Optional live in -> owned -> portable -> fresh-destination loop"
if [[ -n "${MEMANTO_AGENT_ID:-}" ]]; then
  run_memanto agent activate "$MEMANTO_AGENT_ID"
  run_memanto migrate okf "$BUNDLE" --agent "$MEMANTO_AGENT_ID"
  run_golden_recall "$ROOT/reports/primary-golden-recall.txt"
  run_memanto memory export --okf \
    --agent "$MEMANTO_AGENT_ID" \
    --output "$ROUNDTRIP" \
    --limit 1000 \
    --split file
  validate_bundle "$ROUNDTRIP" "$ROOT/reports/live-roundtrip-fidelity.json"

  if [[ -n "${MEMANTO_FRESH_AGENT_ID:-}" ]]; then
    run_memanto agent activate "$MEMANTO_FRESH_AGENT_ID"
    run_memanto migrate okf "$ROUNDTRIP" --agent "$MEMANTO_FRESH_AGENT_ID"
    run_golden_recall "$ROOT/reports/fresh-golden-recall.txt"
    run_memanto memory export --okf \
      --agent "$MEMANTO_FRESH_AGENT_ID" \
      --output "$FRESH_EXPORT" \
      --limit 1000 \
      --split file
    validate_bundle "$FRESH_EXPORT" "$ROOT/reports/fresh-destination-fidelity.json"
    echo "Fresh-destination round trip PASS: $FRESH_EXPORT"
  else
    echo "SKIP second clean destination: set MEMANTO_FRESH_AGENT_ID to another empty activated test agent."
  fi
else
  echo "SKIP live write/export: set MEMANTO_AGENT_ID to an empty Memanto test agent."
fi

echo
echo "PASS: source generation, OKF export, structural validation, and Memanto dry-run completed."
echo "Reports: $ROOT/reports"
