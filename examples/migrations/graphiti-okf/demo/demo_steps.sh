#!/usr/bin/env bash
# Narrated CLI steps for Memanto #1609 Graphiti → OKF showcase (offline + dry-run).
# Paced for ~90–120s social-friendly screen capture.
set -euo pipefail

DEMO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXAMPLE="$DEMO_ROOT"
export PATH="$EXAMPLE/.venv/bin:$PATH"
export TERM="xterm-256color"
export COLORTERM="truecolor"
export COLUMNS="${COLUMNS:-100}"
export LINES="${LINES:-32}"
export FORCE_COLOR=1
export CLICOLOR_FORCE=1

pause() { sleep "${1:-1.5}"; }

typewrite() {
  # Slow echo so viewers can read the command being "typed"
  local s="$1"
  local i
  for ((i=0; i<${#s}; i++)); do
    printf '%s' "${s:i:1}"
    sleep 0.035
  done
  printf '\n'
  sleep 0.4
}

banner() {
  echo
  printf '\033[1;36m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m\n'
  printf '\033[1;37m  %s\033[0m\n' "$*"
  printf '\033[1;36m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m\n'
  echo
}

cd "$EXAMPLE"
# shellcheck disable=SC1091
source .venv/bin/activate

clear 2>/dev/null || true
banner "Memanto #1609 — Graphiti → OKF (offline freedom loop)"
echo "Example: examples/migrations/graphiti-okf"
echo "PR:      https://github.com/moorcheh-ai/memanto/pull/1958"
echo "Goal:    portable Graphiti memories → OKF bundle → Memanto dry-run"
pause 3.5

banner "Step 1 — Offline pipeline: seed → export → adapt → validate"
echo -n "$ "
typewrite "./run.sh offline"
./run.sh offline
pause 4.0

banner "Step 2 — Inspect migration summary"
echo -n "$ "
typewrite "cat out/migration_summary.json"
python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("out/migration_summary.json").read_text())
print(json.dumps(data, indent=2)[:1800])
PY
pause 4.0

banner "Step 3 — Validation report (round-trip checks)"
echo -n "$ "
typewrite "cat out/validation_report.md"
cat out/validation_report.md
pause 3.5

banner "Step 4 — Memanto OKF import preview (dry-run, no API key / no writes)"
echo -n "$ "
typewrite "memanto migrate okf ./out/okf-bundle --dry-run"
memanto migrate okf ./out/okf-bundle --dry-run
pause 4.5

banner "Step 5 — Sample OKF memory markdown files"
echo -n "$ "
typewrite "find out/okf-bundle/memories -name '*.md' ! -name index.md | sort | head"
find out/okf-bundle/memories -type f -name '*.md' ! -name 'index.md' | sort | head -14
pause 3.0

SAMPLES=(
  "out/okf-bundle/memories/preference/prefers-alex-rivera-aisle-seat-e-aisle.md"
  "out/okf-bundle/memories/goal/has-goal-alex-rivera-tokyo-e-tokyo.md"
  "out/okf-bundle/memories/relationship/works-at-alex-rivera-cascadia-labs-e-works.md"
  "out/okf-bundle/memories/event/traveled-to-alex-rivera-denver-e-denver-trip.md"
)
for f in "${SAMPLES[@]}"; do
  if [[ -f "$f" ]]; then
    echo
    printf '\033[1;33m── %s ──\033[0m\n' "$f"
    head -n 22 "$f"
    pause 3.2
  fi
done

banner "Done — Graphiti → OKF → Memanto (dry-run) complete"
echo "Artifacts under examples/migrations/graphiti-okf/out/:"
echo "  • okf-bundle/              portable OKF memories"
echo "  • migration_summary.json   mapping stats"
echo "  • validation_report.md     round-trip checks"
echo
echo "No Moorcheh live key required for this offline + CLI dry-run demo."
pause 5.0
