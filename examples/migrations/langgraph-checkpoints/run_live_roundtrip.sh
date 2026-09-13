#!/usr/bin/env bash
# Thin wrapper: check dual venvs and MOORCHEH_API_KEY, then run the live round trip.
# Never prints the API key value.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

EXAMPLE_PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$EXAMPLE_PYTHON" ]]; then
  EXAMPLE_PYTHON="$ROOT/.venv/bin/python3"
fi
REPO_ROOT="$(cd "$ROOT/../../.." && pwd)"
REPO_PYTHON="$REPO_ROOT/.venv/bin/python"
if [[ ! -x "$REPO_PYTHON" ]]; then
  REPO_PYTHON="$REPO_ROOT/.venv/bin/python3"
fi

if [[ ! -x "$EXAMPLE_PYTHON" ]]; then
  cat >&2 <<'EOF'
Example .venv is missing.
From this directory run:
  python -m venv .venv
  .venv/bin/python -m pip install -e ".[dev]"
EOF
  exit 1
fi

if [[ ! -x "$REPO_PYTHON" ]]; then
  cat >&2 <<'EOF'
Repository-root .venv is missing.
From the memanto repo root run:
  uv sync --group dev
  # or: python -m venv .venv && .venv/bin/python -m pip install -e ".[all]"
EOF
  exit 1
fi

strip_env_value() {
  local value="${1-}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  if [[ ${#value} -ge 2 ]]; then
    local first="${value:0:1}"
    local last="${value: -1}"
    if [[ ( "$first" == '"' && "$last" == '"' ) || ( "$first" == "'" && "$last" == "'" ) ]]; then
      value="${value:1:${#value}-2}"
      value="${value#"${value%%[![:space:]]*}"}"
      value="${value%"${value##*[![:space:]]}"}"
    fi
  fi
  printf '%s' "$value"
}

is_configured_moorcheh_api_key() {
  local cleaned
  cleaned="$(strip_env_value "${1-}")"
  if [[ -z "$cleaned" ]]; then
    return 1
  fi
  local lower candidate
  lower="$(printf '%s' "$cleaned" | tr '[:upper:]' '[:lower:]')"
  for candidate in \
    your_api_key_here \
    your_key_here \
    your_key \
    your-api-key-here \
    changeme \
    replace_me \
    replace-me \
    xxx \
    todo \
    api_key_here \
    insert_api_key_here \
    '<your_api_key>' \
    '<api_key>' \
    none \
    null \
    undefined
  do
    if [[ "$lower" == "$candidate" ]]; then
      return 1
    fi
  done
  return 0
}

read_env_file_moorcheh_api_key() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    return 1
  fi
  local line key value
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    if [[ "$line" == MOORCHEH_API_KEY=* || "$line" == MOORCHEH_API_KEY[[:space:]]*=* ]]; then
      key="${line%%=*}"
      key="${key%"${key##*[![:space:]]}"}"
      [[ "$key" == "MOORCHEH_API_KEY" ]] || continue
      value="${line#*=}"
      printf '%s' "$value"
      return 0
    fi
  done <"$path"
  return 1
}

has_key=0
if [[ -n "${MOORCHEH_API_KEY-}" && -n "${MOORCHEH_API_KEY//[[:space:]]/}" ]]; then
  # Explicit process env wins; placeholders do not count as configured.
  if is_configured_moorcheh_api_key "$MOORCHEH_API_KEY"; then
    has_key=1
  fi
else
  local_val=""
  memanto_val=""
  if local_val="$(read_env_file_moorcheh_api_key "$ROOT/.env")"; then
    :
  else
    local_val=""
  fi
  if memanto_val="$(read_env_file_moorcheh_api_key "${HOME}/.memanto/.env")"; then
    :
  else
    memanto_val=""
  fi
  if is_configured_moorcheh_api_key "$local_val" || is_configured_moorcheh_api_key "$memanto_val"; then
    has_key=1
  fi
fi

if [[ "$has_key" -ne 1 ]]; then
  cat >&2 <<'EOF'
MOORCHEH_API_KEY is not set.
Get a free key at https://moorcheh.ai/ then either:
  export MOORCHEH_API_KEY=your_key
  copy .env.example to .env and fill it in
  or run memanto once to store the key in ~/.memanto/.env
Placeholder values such as your_api_key_here do not count.
Do not commit .env. This script never prints the key value.
EOF
  exit 1
fi

exec "$EXAMPLE_PYTHON" "$ROOT/record_live_terminal.py" "$@"
