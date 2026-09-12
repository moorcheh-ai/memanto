#!/usr/bin/env bash
set -euo pipefail

demo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_file="${1:-$demo_dir/sample/source-session.jsonl}"
output_dir="${2:-$demo_dir/sample/okf}"
golden_file="${3:-$demo_dir/sample/golden_qa.json}"
python_bin="${PYTHON:-python3}"

# The adapter intentionally lives under examples rather than being installed as
# part of Memanto. Make the demo self-contained when invoked from any working
# directory while preserving an existing import path for callers.
export PYTHONPATH="$demo_dir${PYTHONPATH:+:$PYTHONPATH}"

"$python_bin" "$demo_dir/convert.py" "$source_file" "$output_dir"
"$python_bin" -m pytest -q "$demo_dir/tests"
"$python_bin" "$demo_dir/validate.py" \
  "$source_file" "$output_dir" "$golden_file"

if "$python_bin" -c 'import memanto' >/dev/null 2>&1; then
  "$python_bin" -m memanto migrate okf "$output_dir" --dry-run
else
  echo "memanto CLI not found; install the repository to run the dry-run import."
fi
