#!/usr/bin/env bash
# Session B — fresh terminal, no shared in-memory context with Session A.
# Without Memanto, Claude would propose Drizzle (its default).
# With Memanto, Claude references Prisma + the single-schema convention.

set -euo pipefail

cat <<'PROMPT' | claude -p
Write an integration test for the invoice creation endpoint we drafted earlier.
Pick whichever testing setup is conventional in this repo. Explain your choices.
PROMPT

echo
echo "Session B complete. Look for these signals in Claude's response:"
echo "  - mentions Prisma (not Drizzle)"
echo "  - notes the single-schema-per-domain convention"
echo "  - matches the prisma-client-js generator output path"
echo
echo "Inspect ~/.claude/hooks/memanto/logs/inject_context.log to see what was injected."
echo "Then run ./show_memories.sh to dump the persisted memories."
