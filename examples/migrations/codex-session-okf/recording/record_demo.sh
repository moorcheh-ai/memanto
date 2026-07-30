#!/usr/bin/env bash
set -euo pipefail

recording_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
demo_dir="$(cd "$recording_dir/.." && pwd)"
repo_dir="$(cd "$demo_dir/../../.." && pwd)"
memanto_bin="${MEMANTO_BIN:-$(command -v memanto || true)}"
python_bin="${PYTHON:-python3}"
work_dir="$(mktemp -d /tmp/memanto-codex-video-demo.XXXXXX)"
live="${MEMANTO_RECORD_LIVE:-0}"
auto="${MEMANTO_DEMO_AUTO:-0}"

pause() {
  if [[ "$auto" != "1" ]]; then
    printf '\nPress Enter for the next scene...'
    read -r _
  fi
}

scene() {
  clear 2>/dev/null || true
  printf '============================================================\n'
  printf '%s\n' "$1"
  printf '============================================================\n\n'
}

run_memanto() {
  "$memanto_bin" "$@" 2>&1 |
    sed "s#${HOME:?HOME is required}/.memanto#~/.memanto#g"
}

cd "$repo_dir"
scene "SCENE 1 — A real Codex session, without private internals"
printf 'Source: a privacy-safe subset from a genuine Codex rollout\n'
printf 'Records: '
wc -l < "$demo_dir/sample/source-session.jsonl"
printf '\nThe adapter accepts only user/assistant messages and rejects reasoning,\n'
printf 'tool calls, system prompts, credentials, and transport metadata.\n\n'
"$python_bin" - "$demo_dir/sample/source-session.jsonl" <<'PY'
import json
import sys

for number, line in enumerate(open(sys.argv[1], encoding="utf-8"), 1):
    item = json.loads(line)
    payload = item.get("payload", {})
    role = payload.get("role", "unknown")
    text = " ".join(
        part.get("text", "") for part in payload.get("content", [])
        if isinstance(part, dict)
    )
    text = " ".join(text.split())
    print(f"{number}. {role:9} {text[:88]}")
PY
pause

scene "SCENE 2 — Convert Codex JSONL into portable OKF Markdown"
"$python_bin" "$demo_dir/convert.py" \
  "$demo_dir/sample/source-session.jsonl" "$work_dir/okf"
printf '\nGenerated Markdown files:\n'
find "$work_dir/okf/memories" -type f -name '*.md' -not -name index.md \
  -printf '  %P\n' | sort
printf '\nReadable OKF example:\n\n'
sed -n '1,34p' "$work_dir/okf/memories/conversation/002-assistant.md"
pause

scene "SCENE 3 — Privacy tests and source-to-OKF recall parity"
PYTHONPATH="$demo_dir" "$python_bin" -m pytest -q "$demo_dir/tests"
printf '\nGolden validation:\n'
"$python_bin" "$demo_dir/validate.py" \
  "$demo_dir/sample/source-session.jsonl" \
  "$work_dir/okf" \
  "$demo_dir/sample/golden_qa.json"
pause

scene "SCENE 4 — Memanto maps every OKF node before writing"
run_memanto migrate okf "$work_dir/okf" --dry-run

if [[ "$live" != "1" ]]; then
  printf '\nSAFE REHEARSAL COMPLETE — no cloud memories were written.\n'
  printf 'For the recorded live run, set MEMANTO_RECORD_LIVE=1.\n'
  exit 0
fi
pause

agent_id="${MEMANTO_DEMO_AGENT:-codex-okf-video-$(date -u +%Y%m%d-%H%M%S)}"

scene "SCENE 5 — Live import into an isolated Memanto agent"
run_memanto agent create "$agent_id" \
  --pattern tool \
  --description "Recorded Codex to OKF portability demonstration"
run_memanto migrate okf "$work_dir/okf" --agent "$agent_id"
pause

scene "SCENE 6 — The migrated agent remembers the same answers"
run_memanto recall "What date did the assistant report?" --limit 1
run_memanto recall "Which Python project was present in the workspace?" --limit 1
run_memanto recall "Which TypeScript/Node.js project was present?" --limit 1
pause

scene "SCENE 7 — Export everything back to owned, readable OKF"
run_memanto memory export --agent "$agent_id" --okf --split file
printf '\nFREEDOM LOOP COMPLETE\n'
printf 'Codex session -> privacy-filtered OKF -> Memanto -> portable OKF\n'
printf 'Imported memories: 4 | Golden questions: 3/3 | Exported memories: 4\n'
printf '\nAgent used for this recording: %s\n' "$agent_id"
