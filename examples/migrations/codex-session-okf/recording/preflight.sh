#!/usr/bin/env bash
set -euo pipefail

recording_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
demo_dir="$(cd "$recording_dir/.." && pwd)"
repo_dir="$(cd "$demo_dir/../../.." && pwd)"
memanto_bin="${MEMANTO_BIN:-$(command -v memanto || true)}"
python_bin="${PYTHON:-python3}"

pass() { printf 'OK  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1" >&2; exit 1; }

cd "$repo_dir"

test -x "$memanto_bin" || fail "Memanto CLI is unavailable"
pass "Memanto CLI is available"

"$python_bin" -c "import memanto" || fail "Memanto Python package is unavailable"
pass "Memanto Python package is importable"

"$python_bin" - <<'PY'
from memanto.cli.config.manager import ConfigManager

cm = ConfigManager()
if not cm.is_configured():
    raise SystemExit("FAIL  Moorcheh cloud configuration is unavailable")
if cm.get_backend().value != "cloud":
    raise SystemExit("FAIL  Memanto backend is not cloud")
print("OK  Moorcheh cloud configuration is available")
PY

env_file="${MEMANTO_ENV_FILE:-${HOME:?HOME is required}/.memanto/.env}"
test -f "$env_file" || fail "Memanto credential file is missing"
test "$(stat -c %a "$env_file")" = "600" || fail "Credential file mode is not 600"
pass "Credential file permissions are 600"

test -f "$demo_dir/sample/source-session.jsonl" || fail "Public source sample is missing"
test -f "$demo_dir/sample/golden_qa.json" || fail "Golden questions are missing"
pass "Public sample and golden questions are present"

command -v rg >/dev/null 2>&1 ||
  fail "ripgrep is required for the recording safety scan"

if rg -n --pcre2 \
  '(?i)(gh[opusr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{20,}|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})' \
  "$demo_dir/sample" >/dev/null; then
  fail "Public sample contains a credential-like token or email address"
else
  scanner_status=$?
  test "$scanner_status" -eq 1 ||
    fail "Recording safety scan failed with status $scanner_status"
fi
pass "Public sample passes the recording safety scan"

test -z "$(git status --porcelain)" || fail "Repository has uncommitted changes"
pass "Repository is clean"

printf '\nPreflight complete. Safe rehearsal command:\n'
printf '  %s/record_demo.sh\n' "$recording_dir"
printf 'Live recording command (use only while recording):\n'
printf '  MEMANTO_RECORD_LIVE=1 %s/record_demo.sh\n' "$recording_dir"
