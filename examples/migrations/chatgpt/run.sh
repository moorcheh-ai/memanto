#!/usr/bin/env bash
# One-command demo: ChatGPT export -> OKF bundle -> memanto migrate preview.
#
#   ./run.sh                          # uses the committed sample export
#   ./run.sh ~/Downloads/chatgpt-export.zip   # uses YOUR real export
#
# The dry-run preview needs no API key. To import for real afterwards:
#   memanto migrate okf ./out/okf-bundle --agent <agent-id>
#   python3 validation/validate_recall.py --agent <agent-id>
set -euo pipefail
cd "$(dirname "$0")"

SOURCE="${1:-sample_data/chatgpt-export-sample}"
BUNDLE="out/okf-bundle"

if [ ! -e "$SOURCE" ]; then
  echo "Regenerating sample export..."
  python3 make_sample_export.py
fi

echo "==> 1/2 Extracting ChatGPT memory into an OKF bundle"
python3 chatgpt_to_okf.py "$SOURCE" -o "$BUNDLE"

echo
echo "==> 2/2 Previewing the import with the shipped Memanto CLI (dry run)"
memanto migrate okf "$BUNDLE" --dry-run
