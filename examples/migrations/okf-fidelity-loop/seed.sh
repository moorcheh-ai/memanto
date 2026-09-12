#!/usr/bin/env bash
# Regenerate sample/bundle-gen0 from a live Memanto agent. Needs MOORCHEH_API_KEY.
# The committed fixture came from exactly this script; run.sh does not need it.
set -euo pipefail
cd "$(dirname "$0")"

AGENT="${1:-okf-fidelity-loop}"

# Seeding twice would store every memory twice: ids are assigned server-side, so
# a second --batch adds rather than updates. Start from a clean agent.
if memanto agent list 2>/dev/null | grep -Fqw -- "$AGENT"; then
    echo "Agent '$AGENT' already exists. Remove it first:" >&2
    echo "    memanto agent delete $AGENT" >&2
    exit 1
fi

python build_seed.py

memanto agent create "$AGENT"
for batch in seed/batch-*.json; do
    memanto remember --batch "$batch"
done
memanto memory export --okf --agent "$AGENT" --limit 100

mkdir -p sample
rm -rf sample/bundle-gen0
cp -r "$HOME/.memanto/exports/${AGENT}_okf" sample/bundle-gen0
echo "Wrote sample/bundle-gen0 from agent '$AGENT'"
