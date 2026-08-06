#!/usr/bin/env bash
# One-command pipeline: Graphiti → adapter → Memanto → OKF → Mem0 merge → validate.
# Requires: Docker (or GRAPHITI_BACKEND=kuzu), Python 3.10+, and the keys in .env.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "ERROR: .env missing. Copy .env.example → .env and fill in the keys." >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a; source .env; set +a

PYTHON="${PYTHON:-python}"
if [[ -x .venv/bin/python ]]; then
  PYTHON=".venv/bin/python"
elif [[ -x .venv/Scripts/python.exe ]]; then
  PYTHON=".venv/Scripts/python.exe"
fi

AGENT_ID="${MEMANTO_AGENT_ID:-graphiti-okf-demo}"
mkdir -p data data/validation okf_bundle_sample

step() { echo; echo "════════════════════════════════════════"; echo "▶ $*"; echo "════════════════════════════════════════"; }

# ---- backend ---------------------------------------------------------------
if [[ "${GRAPHITI_BACKEND:-neo4j}" == "neo4j" ]]; then
  if command -v docker >/dev/null 2>&1; then
    step "Starting Neo4j (docker compose)"
    docker compose up -d
    echo "Waiting for Neo4j bolt..."
    for i in $(seq 1 60); do
      if docker compose exec -T neo4j cypher-shell -u neo4j -p "${NEO4J_PASSWORD}" 'RETURN 1' >/dev/null 2>&1; then
        break
      fi
      sleep 2
    done
  else
    echo "WARNING: docker not found; set GRAPHITI_BACKEND=kuzu for the zero-Docker fallback," >&2
    echo "         or install Docker Desktop and re-run." >&2
    exit 1
  fi
fi

# ---- Phase 1 ---------------------------------------------------------------
step "Phase 1 — populate Graphiti"
"$PYTHON" scripts/populate_graphiti.py

step "Phase 1 — export raw Graphiti state"
"$PYTHON" scripts/export_graphiti.py

# ---- Phase 2 ---------------------------------------------------------------
step "Phase 2 — adapt Graphiti → OKF + provider JSON"
"$PYTHON" scripts/graphiti_to_memanto.py

step "Phase 2 — dry-run OKF import"
memanto migrate okf data/graphiti_okf_bundle --dry-run | tee data/okf_dry_run.txt

step "Phase 2 — dry-run provider-JSON (savings report)"
memanto migrate mem0 --file data/memanto_provider_import.json --dry-run | tee data/provider_dry_run.txt
# Capture the latest migrate-report.md the CLI just wrote.
REPORT="$(ls -1dt "${HOME}/.memanto/migrate/mem0/"*/migrate-report.md 2>/dev/null | head -n1 || true)"
if [[ -n "${REPORT}" ]]; then
  cp "${REPORT}" data/savings_report.txt
  echo "Saved savings report → data/savings_report.txt"
fi

step "Phase 2 — real OKF import into agent ${AGENT_ID}"
memanto agent create --id "${AGENT_ID}" >/dev/null 2>&1 || true
memanto agent activate "${AGENT_ID}"
memanto migrate okf data/graphiti_okf_bundle --agent "${AGENT_ID}" | tee data/okf_import.txt

# ---- Phase 3 ---------------------------------------------------------------
step "Phase 3 — round-trip validation (Graphiti vs Memanto + Anthropic judge)"
"$PYTHON" scripts/run_validation.py --agent "${AGENT_ID}"

# ---- Phase 4 ---------------------------------------------------------------
step "Phase 4 — export OKF (pre-consolidation)"
rm -rf data/okf_pre_consolidation
memanto memory export --okf --agent "${AGENT_ID}" -o data/okf_pre_consolidation --split file
# Snapshot into git so the consolidation produces a real diff.
if command -v git >/dev/null 2>&1; then
  git add -A data/okf_pre_consolidation >/dev/null 2>&1 || true
fi

step "Phase 4 — populate + migrate second source (Mem0)"
"$PYTHON" scripts/populate_mem0.py
memanto migrate mem0 --file data/mem0_export.json --agent "${AGENT_ID}" --report | tee data/mem0_import.txt

step "Phase 4 — export OKF (post-consolidation) + diff"
rm -rf okf_bundle_sample
memanto memory export --okf --agent "${AGENT_ID}" -o okf_bundle_sample --split file
if command -v git >/dev/null 2>&1; then
  # Diff the pre-consolidation snapshot against the post-consolidation bundle
  # by comparing the two directories directly — no commit required.
  diff -ru data/okf_pre_consolidation okf_bundle_sample > data/consolidation_diff.txt || true
  echo "Consolidation diff → data/consolidation_diff.txt"
fi

step "Done"
echo "Artifacts under data/ and okf_bundle_sample/."
echo "See SUMMARY.md for the wake-up report (written by the packaging step)."
