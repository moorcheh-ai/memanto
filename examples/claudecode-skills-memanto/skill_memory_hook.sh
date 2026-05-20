#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  cat >&2 <<'USAGE'
Usage:
  skill_memory_hook.sh <skill-name> <task-summary> -- <command> [args...]

Example:
  ./skill_memory_hook.sh tdd "Add API pagination tests" -- pytest tests/test_api.py
USAGE
  exit 2
fi

SKILL_NAME="$1"
TASK_SUMMARY="$2"
shift 2

if [[ "${1:-}" != "--" ]]; then
  echo "Expected -- before the command to run." >&2
  exit 2
fi
shift

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRANSCRIPT="${MEMANTO_SKILL_TRANSCRIPT:-$ROOT_DIR/demo/latest-transcript.log}"
BACKEND="${MEMANTO_SKILL_BACKEND:-local}"
STORE="${MEMANTO_SKILL_STORE:-$ROOT_DIR/.memanto-skills-memory.json}"

mkdir -p "$(dirname "$TRANSCRIPT")"

python "$ROOT_DIR/bridge.py" \
  --backend "$BACKEND" \
  --store "$STORE" \
  before \
  --skill "$SKILL_NAME" \
  --task "$TASK_SUMMARY"

{
  echo "$ $*"
  "$@"
} 2>&1 | tee "$TRANSCRIPT"

python "$ROOT_DIR/bridge.py" \
  --backend "$BACKEND" \
  --store "$STORE" \
  after \
  --skill "$SKILL_NAME" \
  --task "$TASK_SUMMARY" \
  --transcript "$TRANSCRIPT"
