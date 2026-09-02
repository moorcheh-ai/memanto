#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INVOCATION_DIR="$PWD"
cd "$SCRIPT_DIR"

echo "=== Universal Migration Adapter ==="
echo ""

if [ ! -f "cli.py" ]; then
    echo "Error: cli.py not found. Run from the project root."
    exit 1
fi

if [ "$#" -lt 2 ]; then
    echo "Usage: ./run.sh <source> <export.json|export.zip>"
    echo ""
    echo "Builds one OKF bundle from a REAL exported chat archive."
    echo ""
    echo "  ./run.sh chatgpt ./chatgpt_export/conversations.json"
    echo "  ./run.sh claude  ./claude_export.zip"
    echo "  ./run.sh gemini  ./gemini_export/conversations.json"
    echo ""
    echo "Then import and close the loop:"
    echo "  memanto migrate okf okf_output/<source> --dry-run"
    echo "  memanto migrate okf okf_output/<source>"
    echo "  memanto memory export --okf -o ~/.memanto/export"
    exit 1
fi

SOURCE="$1"
INPUT="$2"

# Resolve relative paths against the caller's dir, not the script dir.
if [ "${INPUT#/}" = "$INPUT" ]; then
    INPUT="$INVOCATION_DIR/$INPUT"
fi

if [ ! -f "$INPUT" ]; then
    echo "Error: input not found: $INPUT"
    exit 1
fi

echo "[1/2] Converting real $SOURCE export from $INPUT..."
python3 cli.py --source "$SOURCE" --input "$INPUT" --output "okf_output/$SOURCE"

echo ""
echo "[2/2] Importing into Memanto (dry run)..."
python3 -m memanto migrate okf "okf_output/$SOURCE" --dry-run

echo ""
echo "=== Done ==="
echo ""
echo "To actually import (not just preview):"
echo "  memanto migrate okf okf_output/$SOURCE"
echo "To close the portable loop:"
echo "  memanto memory export --okf -o ~/.memanto/export"
