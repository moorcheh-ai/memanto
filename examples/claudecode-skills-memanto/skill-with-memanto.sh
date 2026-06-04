#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# skill-with-memanto.sh
#
# Drop-in wrapper that adds Memanto persistent memory to any
# mattpocock/skills invocation.
#
# Usage:
#   ./skill-with-memanto.sh /tdd src/api/users.ts "Write tests for user signup"
#
# What happens:
#   1. Queries Memanto for memories relevant to the file/task
#   2. Prints the context block (pipe it into your skill prompt)
#   3. After the skill completes, stores the summary in Memanto
#
# Environment variables (export or put in .env):
#   MOORCHEH_API_KEY   — required
#   MEMANTO_AGENT_ID   — default: claudecode-dev
#   MEMANTO_CONTEXT_LIMIT — default: 5
# ──────────────────────────────────────────────────────────────────────

set -euo pipefail

SKILL="${1:?Usage: $0 <skill-name> [file-path] [task-description]}"
FILE="${2:-}"
TASK="${3:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "═══════════════════════════════════════════════════════════════"
echo "  Memanto Cross-Skill Memory — Pre-Skill Context"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Step 1: Query Memanto for relevant context
CONTEXT=$(python -m memanto_skill_hook pre \
    --skill "$SKILL" \
    --file "$FILE" \
    --task "$TASK" 2>/dev/null || true)

if [ -n "$CONTEXT" ]; then
    echo "$CONTEXT"
    echo ""
    echo "───────────────────────────────────────────────────────────────"
    echo "  ↑ Inject the above into your skill's system prompt."
    echo "───────────────────────────────────────────────────────────────"
else
    echo "(No relevant memories found — starting fresh.)"
fi

echo ""
echo "Now run your skill. When done, paste a one-line summary below."
echo "Or press Ctrl+C to skip storing."
echo ""
read -r -p "Summary: " SUMMARY

if [ -n "$SUMMARY" ]; then
    python -m memanto_skill_hook post \
        --skill "$SKILL" \
        --file "$FILE" \
        --summary "$SUMMARY" 2>/dev/null
    echo "✓ Memory stored in Memanto."
fi
