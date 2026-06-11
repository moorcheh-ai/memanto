#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /skill-name [skill arguments...]" >&2
  echo "Example: $0 /tdd add coverage for the billing parser" >&2
  exit 64
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
skill_name="$1"
shift || true

export MEMANTO_SKILL_NAME="${skill_name#/}"

payload="$(python3 - "$skill_name" "$*" <<'PY'
import json
import os
import sys

skill = sys.argv[1]
args = sys.argv[2]
print(json.dumps({"prompt": f"{skill} {args}".strip(), "cwd": os.getcwd()}))
PY
)"

context="$({ printf '%s' "$payload" | python3 "$script_dir/memanto_skill_hook.py" pre; } || true)"

if [[ -n "${context// }" ]]; then
  claude "$skill_name" "$@" --append-system-prompt "$context"
else
  claude "$skill_name" "$@"
fi

printf '%s' "$payload" | python3 "$script_dir/memanto_skill_hook.py" post || true
