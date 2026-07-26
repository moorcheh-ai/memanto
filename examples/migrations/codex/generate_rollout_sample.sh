#!/usr/bin/env bash
set -euo pipefail

EXAMPLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REAL_CODEX_HOME="${CODEX_HOME:-${HOME}/.codex}"
DEMO_HOME="$(mktemp -d "${TMPDIR:-/tmp}/memanto-codex-rollout.XXXXXX")"
SOURCE_EXPORT="${1:-${EXAMPLE_DIR}/out/generated-rollout-export.json}"
OKF_BUNDLE="${2:-${EXAMPLE_DIR}/out/generated-rollout-okf}"

cleanup() {
  rm -rf "${DEMO_HOME}"
}
trap cleanup EXIT

if ! command -v codex >/dev/null 2>&1; then
  printf 'error: codex CLI is not installed\n' >&2
  exit 1
fi

if [[ -f "${REAL_CODEX_HOME}/auth.json" ]]; then
  ln -s "${REAL_CODEX_HOME}/auth.json" "${DEMO_HOME}/auth.json"
fi

PROMPT='Review PROJECT.md without editing files. The team adopted PostgreSQL 16 because workers share state, Python 3.10 as the minimum, UTC for every stored timestamp, and structured JSON production logs. The user prefers concise status updates and wants test failures explained before fixes. Compare the baseline with those decisions and finish with the current rules.'

CODEX_HOME="${DEMO_HOME}" codex exec \
  --ignore-user-config \
  --ignore-rules \
  --disable memories \
  --sandbox read-only \
  --cd "${EXAMPLE_DIR}/sample_project" \
  "${PROMPT}"

ROLLOUT="$(
  find "${DEMO_HOME}/sessions" -type f -name 'rollout-*.jsonl' -print \
    | sort \
    | tail -n 1
)"

if [[ -z "${ROLLOUT}" ]]; then
  printf 'error: Codex completed but no persisted rollout was found\n' >&2
  exit 1
fi

python3 "${EXAMPLE_DIR}/codex_to_okf.py" "${ROLLOUT}" \
  --source-format sessions \
  --output "${OKF_BUNDLE}" \
  --export-source "${SOURCE_EXPORT}" \
  --overwrite

printf 'Generated source export: %s\n' "${SOURCE_EXPORT}"
printf 'Generated OKF bundle: %s\n' "${OKF_BUNDLE}"
