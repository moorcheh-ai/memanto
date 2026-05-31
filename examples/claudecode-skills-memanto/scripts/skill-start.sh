#!/usr/bin/env bash
set -euo pipefail

SKILL="unknown"
TASK=""
PATH_HINT="."
OUT=".memanto-skills/generated/memanto-context.md"
LIMIT="8"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skill) SKILL="$2"; shift 2 ;;
    --task) TASK="$2"; shift 2 ;;
    --path) PATH_HINT="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --limit) LIMIT="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

mkdir -p "$(dirname "$OUT")"
QUERY="Claude Code skill ${SKILL}. Task: ${TASK}. Path: ${PATH_HINT}. Recall relevant engineering decisions, preferences, constraints, gotchas."

{
  echo "## Memanto engineering memory"
  echo
  if command -v memanto >/dev/null 2>&1; then
    memanto recall "$QUERY" --limit "$LIMIT" 2>/dev/null || true
  else
    echo "- memanto CLI not found; run: pip install memanto"
  fi
} > "$OUT"

echo "$OUT"
