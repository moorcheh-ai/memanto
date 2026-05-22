#!/usr/bin/env bash
# skills-memory.sh — Cross-session engineering memory bridge for Claude Code skills
#
# Wraps the mattpocock/skills lifecycle with Memanto memory:
#   pre-skill  → recall relevant engineering decisions
#   post-skill → store distilled summary of what happened
#
# Usage:
#   bash skills-memory.sh recall <topic>           # Inject memories before skill
#   bash skills-memory.sh remember <summary> [opts] # Store memory after skill
#   bash skills-memory.sh wrap <skill-command>      # Full lifecycle wrapper
#   bash skills-memory.sh daily                     # Daily engineering summary
#
# Bounty: https://github.com/moorcheh-ai/memanto/issues/508

set -euo pipefail

# --- Configuration ---
AGENT_NAME="${MEMANTO_AGENT:-claude-code-skills}"
PREVIEW_MODE="${MEMANTO_PREVIEW:-0}"
PREVIEW_DIR="${HOME}/.memanto-preview"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()  { echo -e "${CYAN}[memanto-bridge]${NC} $*"; }
log_ok()    { echo -e "${GREEN}[memanto-bridge]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[memanto-bridge]${NC} $*"; }
log_error() { echo -e "${RED}[memanto-bridge]${NC} $*"; }

# --- Preview mode fallback (no API key needed) ---
preview_remember() {
  local text="$1"
  local tag="${2:-general}"
  mkdir -p "$PREVIEW_DIR"
  local ts
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  TS="$ts" TAG="$tag" MEMORY="$text" python3 - <<'PY' >> "$PREVIEW_DIR/memories.jsonl"
import json
import os

print(json.dumps({
    "timestamp": os.environ["TS"],
    "tag": os.environ["TAG"],
    "memory": os.environ["MEMORY"],
}))
PY
  log_ok "[preview] Memory stored locally ($tag)"
}

preview_recall() {
  local query="$1"
  if [ ! -f "$PREVIEW_DIR/memories.jsonl" ]; then
    log_warn "[preview] No memories stored yet"
    return 0
  fi
  log_info "[preview] Searching memories for: $query"
  # Simple keyword search in preview mode
  QUERY="$query" JSONL_PATH="$PREVIEW_DIR/memories.jsonl" python3 - <<'PY'
import json
import os

query = os.environ['QUERY'].lower()
terms = set(query.split())
results = []
try:
    with open(os.environ['JSONL_PATH']) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            text = entry.get('memory', '').lower()
            score = sum(1 for t in terms if t in text)
            if score > 0:
                results.append((score, entry))
except FileNotFoundError:
    pass
results.sort(key=lambda x: -x[0])
if results:
    for score, entry in results[:5]:
        print(f'  [{score} matches] [{entry.get("tag", "?")}] {entry["memory"][:120]}')
else:
    print('  No matching memories found')
PY
}

# --- Recall: inject relevant memories before skill execution ---
cmd_recall() {
  local query="${1:-}"

  if [ -z "$query" ]; then
    log_warn "Usage: skills-memory.sh recall <topic>"
    return 1
  fi

  if [ "$PREVIEW_MODE" = "1" ]; then
    preview_recall "$query"
    return 0
  fi

  log_info "Recalling engineering memories for: $query"

  # Use memanto CLI to recall relevant memories
  local result
  result=$(memanto recall "$query" --agent "$AGENT_NAME" 2>&1) || {
    log_error "Recall failed. Set MEMANTO_PREVIEW=1 for local mode."
    return 1
  }

  if [ -n "$result" ]; then
    echo "--- Engineering Memory Context ---"
    echo "$result"
    echo "--- End Memory Context ---"
    log_ok "Memories injected"
  else
    log_info "No relevant memories found (this may be the first session)"
  fi
}

# --- Remember: store distilled engineering decision after skill ---
cmd_remember() {
 local text="${1:-}"
 local tag="general"

 if [ -z "$text" ]; then
 log_warn "Usage: skills-memory.sh remember <summary> [--tag <category>]"
 return 1
 fi

 # Parse --tag option (supports: remember "text" --tag security)
 # Shift past the first positional arg (text), then process flags
 shift
 while [ "$#" -gt 0 ]; do
 case "$1" in
 --tag)
 if [ -z "${2:-}" ]; then
 log_warn "Missing value for --tag"
 return 1
 fi
 tag="$2"
 shift 2
 ;;
 *)
 log_warn "Unknown argument: $1"
 return 1
 ;;
 esac
 done

  # Auto-tag based on content heuristics
  local lower
  lower=$(echo "$text" | tr '[:upper:]' '[:lower:]')
  if [ "$tag" = "general" ]; then
    if echo "$lower" | grep -qE "architect|design|pattern|structure|layout"; then
      tag="architecture"
    elif echo "$lower" | grep -qE "prefer|style|convention|naming|format"; then
      tag="coding-style"
    elif echo "$lower" | grep -qE "database|schema|migration|sql|query"; then
      tag="database"
    elif echo "$lower" | grep -qE "deploy|ci/cd|pipeline|infra|server"; then
      tag="infrastructure"
    elif echo "$lower" | grep -qE "auth|secur|token|encrypt|permission"; then
      tag="security"
    elif echo "$lower" | grep -qE "test|spec|assert|coverage|tdd"; then
      tag="testing"
    fi
  fi

  if [ "$PREVIEW_MODE" = "1" ]; then
    preview_remember "$text" "$tag"
    return 0
  fi

  log_info "Storing engineering memory [$tag]..."

  local result
  result=$(memanto remember "$text" --agent "$AGENT_NAME" --tag "$tag" 2>&1) || {
    log_error "Remember failed. Set MEMANTO_PREVIEW=1 for local mode."
    return 1
  }

  log_ok "Memory stored: $tag"
}

# --- Distill: extract engineering decisions from skill output ---
distill_output() {
  local output="$1"
  python3 -c "
import sys, re
text = sys.stdin.read()
# Extract key decisions: lines with 'use', 'prefer', 'choose', 'decided', 'should', 'must'
patterns = [
    r'(?:use|using|prefer|choose|chose|decided|should|must|will|always|never)\s+.+',
    r'(?:architecture|pattern|approach|strategy|convention|style)\s*:.+',
]
decisions = []
for line in text.split('\n'):
    line = line.strip()
    if not line or line.startswith('#') or len(line) < 15:
        continue
    for p in patterns:
        if re.search(p, line, re.IGNORECASE):
            decisions.append(line)
            break
if decisions:
    for d in decisions[:10]:
        print(d)
else:
    # Fallback: first 3 meaningful lines
    lines = [l.strip() for l in text.split('\n') if l.strip() and len(l.strip()) > 20][:3]
    for l in lines:
        print(l)
" <<< "$output"
}

# --- Wrap: full lifecycle wrapper for any skill command ---
cmd_wrap() {
  local skill_cmd="${1:-}"

  if [ -z "$skill_cmd" ]; then
    log_warn "Usage: skills-memory.sh wrap <skill-command>"
    return 1
  fi

  # Extract topic from command for recall
  local topic
  topic=$(echo "$skill_cmd" | sed 's/[^a-zA-Z0-9 ]/ /g' | tr -s ' ' | cut -c1-80)

  # Phase 1: Pre-skill — recall relevant memories
 log_info "=== Pre-skill: Recalling engineering context ==="
 local recalled_context
 recalled_context=$(cmd_recall "$topic" 2>&1) || true
 if [ -n "$recalled_context" ]; then
 echo "$recalled_context"
 fi

 # Phase 2: Execute skill
 log_info "=== Executing skill ==="
 local output
 local skill_status=0
 output=$(eval "$skill_cmd" 2>&1) || skill_status=$?
 echo "$output"

  # Phase 3: Post-skill — distill and store
  log_info "=== Post-skill: Distilling engineering decisions ==="
  local distilled
  distilled=$(distill_output "$output")

  if [ -n "$distilled" ]; then
    while IFS= read -r line; do
      [ -n "$line" ] && cmd_remember "$line" 2>&1 || true
    done <<< "$distilled"
    log_ok "Engineering decisions stored for future sessions"
  else
    log_info "No extractable engineering decisions found in output"
  fi

  return "$skill_status"
}

# --- Daily: summary of today's engineering activity ---
cmd_daily() {
  if [ "$PREVIEW_MODE" = "1" ]; then
    log_info "[preview] Daily summary:"
    preview_recall "all"
    return 0
  fi

  log_info "Generating daily engineering summary..."
  memanto daily-summary --agent "$AGENT_NAME" 2>&1 || {
    log_warn "Daily summary unavailable"
  }
}

# --- Distill-and-remember: distill raw output then store (for PostToolUse hooks) ---
cmd_distill_and_remember() {
  local raw_output="${1:-}"

  if [ -z "$raw_output" ]; then
    return 0
  fi

  local distilled
  distilled=$(distill_output "$raw_output")

  if [ -n "$distilled" ]; then
    while IFS= read -r line; do
      [ -n "$line" ] && cmd_remember "$line" 2>&1 || true
    done <<< "$distilled"
    log_ok "Distilled engineering decisions stored"
  fi
}

# --- Main ---
case "${1:-help}" in
 recall) shift; cmd_recall "$@" ;;
 remember) shift; cmd_remember "$@" ;;
 distill-and-remember) shift; cmd_distill_and_remember "$@" ;;
 wrap) shift; cmd_wrap "$@" ;;
 daily) shift; cmd_daily "$@" ;;
  help|--help|-h)
    echo "skills-memory.sh — Cross-session engineering memory for Claude Code skills"
    echo ""
 echo "Commands:"
 echo " recall <topic> Inject relevant memories before a skill"
 echo " remember <summary> [--tag <category>] Store an engineering decision after a skill"
 echo " distill-and-remember <raw> Distill raw output and store decisions (for hooks)"
 echo " wrap <skill-command> Full pre/post lifecycle wrapper"
 echo " daily Daily engineering summary"
    echo ""
    echo "Environment:"
    echo "  MEMANTO_PREVIEW=1        Local preview mode (no API key needed)"
    echo "  MEMANTO_AGENT=name       Agent namespace (default: claude-code-skills)"
    ;;
  *)
    log_error "Unknown command: $1"
    echo "Run 'skills-memory.sh help' for usage"
    exit 1
    ;;
esac
