#!/usr/bin/env bash
# The live freedom loop: preview the import, run it into a second agent, then
# ask both agents the same questions. Needs MOORCHEH_API_KEY and the agent that
# seed.sh created. Writes the two evidence files under sample/.
set -euo pipefail
cd "$(dirname "$0")"

SOURCE="${1:-okf-fidelity-loop}"
TARGET="${2:-okf-fidelity-rt}"

if memanto agent list 2>/dev/null | grep -Fqw -- "$TARGET"; then
    echo "Agent '$TARGET' already exists; importing again would duplicate it." >&2
    echo "    memanto agent delete $TARGET" >&2
    exit 1
fi

memanto migrate okf ./sample/bundle-gen0 --dry-run | tee sample/migration-summary.txt

memanto agent create "$TARGET"
memanto migrate okf ./sample/bundle-gen0 --agent "$TARGET" | tee -a sample/migration-summary.txt

python validate_recall.py --source "$SOURCE" --target "$TARGET" \
    --out sample/recall-parity.md
