#!/usr/bin/env bash
set -euo pipefail

demo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_file="${1:-$demo_dir/sample/source-session.jsonl}"
output_dir="${2:-$demo_dir/sample/okf}"
python_bin="${PYTHON:-python3}"

"$python_bin" "$demo_dir/convert.py" "$source_file" "$output_dir"
"$python_bin" -m pytest -q "$demo_dir/tests"
"$python_bin" "$demo_dir/validate.py" \
  "$source_file" "$output_dir" "$demo_dir/sample/golden_qa.json"

if command -v memanto >/dev/null 2>&1; then
  memanto migrate okf "$output_dir" --dry-run --report
else
  echo "memanto CLI not found; install the repository to run the dry-run import."
fi
