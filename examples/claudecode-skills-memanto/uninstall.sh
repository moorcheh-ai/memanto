#!/usr/bin/env bash
set -euo pipefail

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SETTINGS="$CLAUDE_DIR/settings.json"

if [[ ! -f "$SETTINGS" ]]; then
  echo "settings_not_found=$SETTINGS"
  exit 0
fi

python3 - "$SETTINGS" <<'PY'
import json
import sys
from pathlib import Path

settings_path = Path(sys.argv[1])
settings = json.loads(settings_path.read_text(encoding="utf-8"))
hooks = settings.get("hooks", {})

for event, entries in list(hooks.items()):
    kept = []
    for entry in entries:
        commands = [hook.get("command", "") for hook in entry.get("hooks", [])]
        if any("skill_memory_bridge.py" in command for command in commands):
            continue
        kept.append(entry)
    if kept:
        hooks[event] = kept
    else:
        hooks.pop(event, None)

if not hooks:
    settings.pop("hooks", None)

settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
PY

echo "removed_memanto_claude_hooks=$SETTINGS"
