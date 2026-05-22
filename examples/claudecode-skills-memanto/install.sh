#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SETTINGS="$CLAUDE_DIR/settings.json"
BACKUP="$SETTINGS.memanto-backup.$(date +%Y%m%d%H%M%S)"

mkdir -p "$CLAUDE_DIR"

if [[ -f "$SETTINGS" ]]; then
  cp "$SETTINGS" "$BACKUP"
else
  printf '{}\n' > "$SETTINGS"
fi

python3 - "$SETTINGS" "$ROOT/skill_memory_bridge.py" <<'PY'
import json
import sys
from pathlib import Path

settings_path = Path(sys.argv[1])
bridge = Path(sys.argv[2]).resolve()

try:
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
except json.JSONDecodeError:
    raise SystemExit(f"Invalid JSON in {settings_path}")

hooks = settings.setdefault("hooks", {})
snippet = {
    "UserPromptSubmit": {
        "matcher": "",
        "hooks": [
            {
                "type": "command",
                "command": f'python3 "{bridge}" inject --skill claude-code --task "$CLAUDE_USER_PROMPT" --cwd "$PWD"',
            }
        ],
    },
    "Stop": {
        "matcher": "",
        "hooks": [
            {
                "type": "command",
                "command": f'python3 "{bridge}" run-skill --skill claude-code --task "$CLAUDE_USER_PROMPT" --cwd "$PWD" --output "$(cat)"',
            }
        ],
    },
}

for event, entry in snippet.items():
    existing = hooks.setdefault(event, [])
    command = entry["hooks"][0]["command"]
    if not any(
        hook.get("command") == command
        for item in existing
        for hook in item.get("hooks", [])
    ):
        existing.append(entry)

settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
PY

echo "installed_memanto_claude_hooks=$SETTINGS"
if [[ -f "$BACKUP" ]]; then
  echo "backup=$BACKUP"
fi
