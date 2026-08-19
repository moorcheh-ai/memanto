#!/usr/bin/env bash
# End-to-end reproducible migration demo for the ChatGPT/Claude memory adapter.
#
# The full "in -> owned -> portable" loop in one command:
#   1. Generate the source archives      (scripts/sample_conversations.py)
#   2. Map them into Memanto memory      (scripts/run_migration.py)
#   3. Export the mapped memories as OKF (real Memanto OKFExporter)
#   4. Print the migration summary + per-type breakdown
#   5. Run round-trip validation         (scripts/roundtrip_check.py)
#
# Everything is offline/local — no API key required. The adapter and exporter
# run against the installed `memanto` package directly.
set -euo pipefail
cd "$(dirname "$0")"

# --- resolve a Python that can import memanto + its deps -----------------
# Prefer the repo's venv (this demo lives inside a memanto checkout at
# <repo>/examples/migrations/<name>); else fall back to a self-contained
# .venv built from requirements.txt so a stranger can run it without the
# whole SDK installed.
REPO_VENV="$(cd "$(dirname "$0")" && cd ../../.. && pwd)/.venv/bin/python"
if [ -x "$REPO_VENV" ] && "$REPO_VENV" -c "import memanto" 2>/dev/null; then
  PY="$REPO_VENV"
elif [ -x ".venv/bin/python" ] && .venv/bin/python -c "import memanto" 2>/dev/null; then
  PY=".venv/bin/python"
else
  echo "==> Creating local .venv from requirements.txt (one time)..."
  python3 -m venv .venv
  ./.venv/bin/pip --quiet install -r requirements.txt
  PY=".venv/bin/python"
fi
echo "Using interpreter: $PY"

echo "==> [1/5] Generating source archives (Claude + ChatGPT exports)"
"$PY" scripts/sample_conversations.py

echo "==> [2/5] Mapping source conversations -> Memanto memory"
"$PY" scripts/run_migration.py

echo "==> [3/5] Exporting mapped memory as an OKF bundle"
"$PY" scripts/run_migration.py --export-okf

echo "==> [4/5] Migration summary + type breakdown (see output above)"

echo "==> [5/5] Round-trip validation (recall parity check)"
"$PY" scripts/roundtrip_check.py

echo ""
echo "Done. OKF bundle: okf/"
