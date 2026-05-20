#!/usr/bin/env bash
# Uninstaller — removes hooks, restores the most-recent settings backup.
# Does NOT delete memories from Memanto (recoverable from the dashboard).

set -euo pipefail

TARGET_DIR="${HOME}/.claude/hooks/memanto"
SETTINGS="${HOME}/.claude/settings.json"

if [[ -d "${TARGET_DIR}" ]]; then
    rm -rf "${TARGET_DIR}"
    echo "▸ Removed ${TARGET_DIR}"
fi

# Find most recent backup
latest_backup="$(ls -t "${SETTINGS}.bak."* 2>/dev/null | head -n1 || true)"
if [[ -n "${latest_backup}" ]]; then
    mv "${latest_backup}" "${SETTINGS}"
    echo "▸ Restored settings.json from ${latest_backup}"
else
    echo "▸ No backup of settings.json found — leaving it as-is (you may want to remove memanto hook entries manually)."
fi

echo "✓ Uninstall complete. Memories in Memanto were left intact."
