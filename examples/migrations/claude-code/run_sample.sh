#!/usr/bin/env bash
set -euo pipefail

example_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${example_dir}/../../.." && pwd)"
output_root="${1:-${example_dir}/sample_output}"
claude_home="${example_dir}/sample_data/.claude"
project="/Users/demo/Projects/auto-planmaxxer"
project_data="${claude_home}/projects/-Users-demo-Projects-auto-planmaxxer"

cd "${repo_root}"

uv run python "${example_dir}/claude_code_to_okf.py" \
  --claude-home "${claude_home}" \
  --project "${project}" \
  --project-data "${project_data}" \
  --output "${output_root}/okf" \
  --force

uv run python "${example_dir}/validation/validate_recall.py" \
  --source-home "${claude_home}" \
  --project "${project}" \
  --project-data "${project_data}" \
  --okf "${output_root}/okf" \
  --questions "${example_dir}/validation/golden_qa.json" \
  --report "${output_root}/recall_parity.json"

uv run memanto migrate okf "${output_root}/okf" --dry-run

if [[ -n "${MEMANTO_LIVE_AGENT:-}" ]]; then
  uv run memanto migrate okf "${output_root}/okf" \
    --agent "${MEMANTO_LIVE_AGENT}"
  uv run python "${example_dir}/validation/validate_live_recall.py" \
    --agent "${MEMANTO_LIVE_AGENT}" \
    --questions "${example_dir}/validation/golden_qa.json" \
    --report "${output_root}/live_recall.json"
fi
