#!/usr/bin/env bash
# End-to-end: assistant export -> OKF bundle -> Memanto -> OKF again.
#
#   bash run.sh <agent-id> [export.zip]
#
# With no export argument this runs against sample/, which finishes in about a
# minute. Every conversation costs one extraction call, so real exports are
# capped at LIMIT threads; raise it once you have seen the output.
#
#   LIMIT=100  bash run.sh my-agent ~/Downloads/chatgpt-export.zip
#   SAVED=my_memories.txt  bash run.sh my-agent ~/Downloads/export.zip
#   CLAUDE=~/Downloads/claude-export.zip  bash run.sh my-agent
#   FRESH=1    bash run.sh my-agent        # reset the agent first
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
[ -f .env ] && { set -a; . ./.env; set +a; }

AGENT="${1:-chatgpt-claude-okf}"
EXPORT="${2:-}"
LIMIT="${LIMIT:-25}"
SAVED="${SAVED:-}"
CLAUDE="${CLAUDE:-}"
REPO="$(cd ../../.. && pwd)"

# Fail on a mistyped path before creating or activating anything. liberate.py
# validates authoritatively; this only stops us doing side effects first.
for pair in "EXPORT:$EXPORT" "CLAUDE:$CLAUDE" "SAVED:$SAVED"; do
  name="${pair%%:*}"; path="${pair#*:}"
  if [ -n "$path" ] && [ ! -e "$path" ]; then
    echo "ERROR: \$$name points at a path that does not exist: $path" >&2
    exit 1
  fi
done

# Resolve the CLI: prefer an activated env, fall back to the repo's .venv.
if command -v memanto >/dev/null 2>&1; then
  MEMANTO=memanto
  PY=python
elif [ -x "$REPO/.venv/bin/memanto" ]; then
  MEMANTO="$REPO/.venv/bin/memanto"
  PY="$REPO/.venv/bin/python"
  echo "(using $REPO/.venv)"
else
  echo "ERROR: the 'memanto' CLI is not installed." >&2
  echo "  python -m venv .venv && source .venv/bin/activate" >&2
  echo "  pip install -r requirements.txt" >&2
  exit 1
fi

: "${MOORCHEH_API_KEY:?set MOORCHEH_API_KEY (cp .env.example .env)}"

echo "==> 1/5  Agent '$AGENT'"
# Memories accumulate across runs, so a second run against the same agent would
# report inflated totals. FRESH=1 starts from an empty agent, which is what you
# want when recording the demo or quoting migration numbers.
if [ "${FRESH:-0}" = "1" ]; then
  echo "    FRESH=1, deleting '$AGENT' first"
  # --force skips the delete confirmation but still asks whether to keep cloud
  # memories, so answer it: 'n' purges them and keeps totals honest.
  printf 'n\n' | "$MEMANTO" agent delete "$AGENT" --force >/dev/null 2>&1 || true
fi
if ! create_output=$("$MEMANTO" agent create "$AGENT" --pattern tool 2>&1); then
  # Only an existing agent is survivable; anything else is a real failure.
  if echo "$create_output" | grep -qi "already exists"; then
    echo "    (already exists, re-run with FRESH=1 for clean totals)"
  else
    echo "$create_output" >&2
    exit 1
  fi
fi
"$MEMANTO" agent activate "$AGENT"

echo "==> 2/5  Building the OKF bundle"
args=(--agent "$AGENT" --out okf_bundle)
if [ -n "$EXPORT" ] || [ -n "$CLAUDE" ]; then
  # Either source alone is fine; together they merge into one bundle.
  [ -n "$EXPORT" ] && args+=(--chatgpt "$EXPORT")
  [ -n "$CLAUDE" ] && args+=(--claude "$CLAUDE")
  args+=(--limit "$LIMIT")
  # Saved memories never appear in an official export, so fold them in when
  # the user has pasted them somewhere.
  [ -n "$SAVED" ] && args+=(--saved "$SAVED")
else
  args+=(
    --chatgpt sample/chatgpt_export.json
    --claude sample/claude_export.json
    --saved sample/saved_memories.txt
  )
fi
"$PY" liberate.py "${args[@]}"

echo "==> 3/5  Preview (no writes)"
"$MEMANTO" migrate okf ./okf_bundle --dry-run

echo "==> 4/5  Import"
"$MEMANTO" migrate okf ./okf_bundle --agent "$AGENT"

echo "==> 5/5  Export back out, the memories are still yours"
"$MEMANTO" memory export --okf --agent "$AGENT"

echo
echo "Done. Verify recall parity with:"
echo "  $PY validate.py --agent $AGENT"
