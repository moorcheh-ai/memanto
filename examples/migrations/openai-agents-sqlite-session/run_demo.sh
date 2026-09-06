#!/usr/bin/env bash
#
# One-command reproduction of the whole migration.
#
#   ./run_demo.sh
#
# Runs, end to end, in a temporary workspace that is deleted on exit:
#   1. a fresh real OpenAI Agents SDK session (agents.Runner + SQLiteSession)
#   2. the OKF 0.2 adapter over that database
#   3. Memanto's real `migrate okf --dry-run` import path
#   4. the committed-artifact verifier
#   5. offline before/after query parity over the run's own bundle
#
# Needs `pip install -r requirements.txt` and the memanto package importable.
# Never writes to sample/ — the committed artifacts are left untouched.
#
# Env: PYTHON=<interpreter> to pick a specific Python.

set -euo pipefail

cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/okf-demo-XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

# Keep Memanto's run directory inside the workspace instead of the real ~/.memanto.
export HOME="$WORK/home"
mkdir -p "$HOME"

step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

step "1/5  Generate a real SQLiteSession with the OpenAI Agents SDK"
"$PYTHON" generate_session.py \
    --db "$WORK/agent_sessions.db" \
    --snapshot "$WORK/session_snapshot.json"

step "2/5  Convert it to an OKF 0.2 bundle"
# Record the source version actually installed, so the report is self-describing.
SDK_VERSION="$("$PYTHON" -c 'from importlib.metadata import version; print(version("openai-agents"))')"
"$PYTHON" okf_adapter.py --db "$WORK/agent_sessions.db" --list-sessions
"$PYTHON" okf_adapter.py \
    --db "$WORK/agent_sessions.db" \
    --session workspace-buddy-demo \
    --out "$WORK/okf" \
    --report "$WORK/report.json" \
    --source-package-version "$SDK_VERSION"

step "3/5  Import it through Memanto (dry run — no credentials needed)"
"$PYTHON" -m memanto migrate okf "$WORK/okf" --dry-run

step "4/5  Verify the committed sample artifacts"
"$PYTHON" verify_artifacts.py

step "5/5  Offline before/after query parity for this run's own bundle"
# Not live Moorcheh recall: a transparent lexical retrieval over the raw SDK
# items and the memories Memanto would store. See parity_check.py.
"$PYTHON" parity_check.py \
    --snapshot "$WORK/session_snapshot.json" \
    --bundle "$WORK/okf" \
    --report "$WORK/report.json" \
    --json "$WORK/query-parity.json"

step "Counts from this run"
"$PYTHON" - "$WORK/report.json" <<'PY'
import json, sys

report = json.load(open(sys.argv[1]))
counts, source = report["counts"], report["source"]
print(f"  source tool      : {source['tool']} {source['package_version']}")
print(f"  session          : {source['session_id']}")
print(f"  read snapshot    : {source['read_snapshot_sha256'][:16]}…")
print(f"  source items     : {counts['source_items']}")
print(f"  mapped documents : {counts['mapped_documents']}  {counts['mapped_by_kind']}")
print(f"  skipped items    : {counts['skipped_items']}  {counts['skipped_by_reason']}")
print(f"  memanto types    : {counts['memanto_type_hints']}")
consumed, total = counts["source_items_consumed"], counts["source_items"]
if consumed != total:
    sys.exit(f"  FAIL: {consumed} of {total} source items accounted for")
print("  every source item accounted for: OK")
PY

printf '\n\033[1mDone.\033[0m Workspace %s removed; sample/ untouched.\n' "$WORK"
