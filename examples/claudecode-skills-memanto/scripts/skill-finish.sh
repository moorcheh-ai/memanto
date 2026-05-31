#!/usr/bin/env bash
set -euo pipefail

SKILL="unknown"
SUMMARY_FILE=""
TAGS="claude-code,skills,memanto"
SOURCE="claude_code"
TYPE="context"
CONFIDENCE="0.9"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skill) SKILL="$2"; shift 2 ;;
    --summary-file) SUMMARY_FILE="$2"; shift 2 ;;
    --tags) TAGS="$2"; shift 2 ;;
    --source) SOURCE="$2"; shift 2 ;;
    --type) TYPE="$2"; shift 2 ;;
    --confidence) CONFIDENCE="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$SUMMARY_FILE" || ! -f "$SUMMARY_FILE" ]]; then
  echo "--summary-file is required" >&2
  exit 2
fi

SUMMARY="$(sed -e 's/[[:space:]]\+/ /g' "$SUMMARY_FILE" | head -c 4000)"
MEMORY="Claude Code skill '${SKILL}' completed. Durable engineering context: ${SUMMARY}"

if command -v memanto >/dev/null 2>&1; then
  memanto remember "$MEMORY" \
    --type "$TYPE" \
    --tags "$TAGS" \
    --confidence "$CONFIDENCE" \
    --provenance observed \
    --source "$SOURCE"
else
  echo "memanto CLI not found; run: pip install memanto" >&2
  exit 127
fi
