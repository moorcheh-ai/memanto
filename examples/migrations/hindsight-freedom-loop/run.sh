#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$ROOT/../../.." && pwd)"

cd "$ROOT"
python build_sample_archive.py

python - <<'PY'
from pathlib import Path
import json
from hindsight_mapper import export_hindsight_to_okf

showcase = Path(".")
archive = showcase / "sample-data" / "project-atlas-agent.zip"
okf_dir = showcase / "sample-data" / "okf-bundle"
result = export_hindsight_to_okf(archive, okf_dir, agent_id="project-atlas-agent")
print(json.dumps(result["migration_summary"], indent=2))
PY

python -m pytest tests/ -q -c pytest.ini || exit 1
python validation/validate_roundtrip.py || exit 1

echo ""
echo "OKF bundle ready at: $ROOT/sample-data/okf-bundle"
echo "Next: memanto migrate okf $ROOT/sample-data/okf-bundle --agent-id project-atlas-agent --dry-run"
