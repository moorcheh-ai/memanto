#!/usr/bin/env bash
# Full pipeline: migrate sample data → export OKF bundle
#
# Requires:
#   MOORCHEH_API_KEY  — set in .env (auto-sourced) or exported in shell
#   AGENT_ID          — set below or pass as first argument
#
# Usage:
#   bash scripts/seed_and_export.sh [agent-id]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHOWCASE_DIR="$(dirname "$SCRIPT_DIR")"
SAMPLE_DATA="$SHOWCASE_DIR/sample_data"
OKF_DIR="$SHOWCASE_DIR/okf_bundle"

# Auto-source .env from the showcase dir or repo root if present
for _env_candidate in "$SHOWCASE_DIR/.env" "$SHOWCASE_DIR/../../.env" "$SHOWCASE_DIR/../../../.env"; do
  if [ -f "$_env_candidate" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$_env_candidate"
    set +a
    break
  fi
done

# ── configure ────────────────────────────────────────────────────────────────
AGENT_ID="${1:-${AGENT_ID:-ai-conversations-showcase}}"
# ─────────────────────────────────────────────────────────────────────────────

if [ -z "${MOORCHEH_API_KEY:-}" ]; then
  echo "ERROR: MOORCHEH_API_KEY is not set." >&2
  echo "       Export it or add it to .env and source it first." >&2
  exit 1
fi

echo ""
echo "========================================"
echo " ai-conversations showcase pipeline"
echo " Agent: $AGENT_ID"
echo "========================================"
echo ""

# Step 1 — create and activate agent
echo ">> Step 1: create and activate agent '$AGENT_ID'"
create_out=$(memanto agent create "$AGENT_ID" --pattern tool 2>&1) && true
create_exit=$?
if [ $create_exit -ne 0 ]; then
  if echo "$create_out" | grep -qi "already exists"; then
    echo "   (agent already exists)"
  else
    echo "ERROR: agent creation failed: $create_out" >&2
    exit 1
  fi
fi
memanto agent activate "$AGENT_ID"
echo ""

# Step 2 — migrate ChatGPT sample data
echo ">> Step 2: migrate ChatGPT sample data"
memanto migrate conversations "$SAMPLE_DATA/chatgpt_export.zip" \
  --source chatgpt --agent "$AGENT_ID"
echo ""

# Step 3 — migrate Claude sample data
echo ">> Step 3: migrate Claude sample data"
memanto migrate conversations "$SAMPLE_DATA/claude_export.zip" \
  --source claude --agent "$AGENT_ID"
echo ""

# Step 4 — migrate Gemini sample data
echo ">> Step 4: migrate Gemini sample data"
memanto migrate conversations "$SAMPLE_DATA/gemini_export.zip" \
  --source gemini --agent "$AGENT_ID"
echo ""

# Step 5 — migrate LangGraph demo data (seeds InMemoryStore automatically)
echo ">> Step 5: migrate LangGraph demo data"
python3 "$SCRIPT_DIR/migrate_langgraph.py" --agent "$AGENT_ID"
echo ""

# Step 6 — export OKF bundle
# The export command writes to ~/.memanto/exports/<agent>_okf/
# We copy the result into the showcase directory so it's committable.
echo ">> Step 6: export OKF bundle"
EXPORT_NAME="${AGENT_ID}_okf"
MEMANTO_EXPORT_DIR="${HOME}/.memanto/${EXPORT_NAME}"
rm -rf "$MEMANTO_EXPORT_DIR"
memanto memory export --okf --output "$EXPORT_NAME" --agent "$AGENT_ID"
echo ""

echo ">> Copying OKF bundle to $OKF_DIR"
rm -rf "$OKF_DIR"
cp -r "$MEMANTO_EXPORT_DIR" "$OKF_DIR"
echo "   Copied $(find "$OKF_DIR" -name "*.md" | wc -l) markdown files"
echo ""

echo "========================================"
echo " Pipeline complete"
echo " OKF bundle: $OKF_DIR"
echo "========================================"
