#!/usr/bin/env bash
set -euo pipefail

EXAMPLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${EXAMPLE_DIR}/../../.." && pwd)"
SOURCE="${1:-${EXAMPLE_DIR}/sample_data/codex-memory-export.json}"
OUT_DIR="${OUTPUT_DIR:-${EXAMPLE_DIR}/out}"
OKF_BUNDLE="${OUT_DIR}/okf-bundle"
PORTABLE_BUNDLE="${OUT_DIR}/memanto-exported-okf"
OFFLINE_REPORT="${OUT_DIR}/recall_report.json"
LIVE_REPORT="${OUT_DIR}/live_recall_report.json"

if command -v memanto >/dev/null 2>&1; then
  MEMANTO=(memanto)
elif command -v uv >/dev/null 2>&1 && [[ -f "${REPO_ROOT}/pyproject.toml" ]]; then
  MEMANTO=(uv run --project "${REPO_ROOT}" memanto)
else
  printf 'error: install memanto or run this example from the repository with uv\n' >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"

python3 "${EXAMPLE_DIR}/codex_to_okf.py" "${SOURCE}" \
  --output "${OKF_BUNDLE}" \
  --overwrite

"${MEMANTO[@]}" migrate okf "${OKF_BUNDLE}" --dry-run

python3 "${EXAMPLE_DIR}/validation/validate_recall.py" \
  --source "${SOURCE}" \
  --bundle "${OKF_BUNDLE}" \
  --report "${OFFLINE_REPORT}"

if [[ -z "${MEMANTO_AGENT:-}" ]]; then
  printf '\nDry-run complete. Set MEMANTO_AGENT to run live import, recall, and export.\n'
  exit 0
fi

"${MEMANTO[@]}" migrate okf "${OKF_BUNDLE}" --agent "${MEMANTO_AGENT}"
"${MEMANTO[@]}" memory export \
  --agent "${MEMANTO_AGENT}" \
  --okf \
  --split file \
  --output "${PORTABLE_BUNDLE}"

python3 "${EXAMPLE_DIR}/validation/validate_live_recall.py" \
  --agent "${MEMANTO_AGENT}" \
  --report "${LIVE_REPORT}"

python3 "${EXAMPLE_DIR}/validation/validate_recall.py" \
  --source "${SOURCE}" \
  --bundle "${PORTABLE_BUNDLE}" \
  --report "${OUT_DIR}/exported_okf_recall_report.json"

printf '\nFull freedom loop complete: %s\n' "${PORTABLE_BUNDLE}"

