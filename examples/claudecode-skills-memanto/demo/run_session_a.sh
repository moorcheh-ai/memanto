#!/usr/bin/env bash
# Session A — drives Claude Code headlessly to establish architectural decisions
# that Session B will then recall.
#
# Prerequisite: `claude` CLI on PATH and authenticated (`claude auth status`).

set -euo pipefail

cat <<'PROMPT' | claude -p
I'm building a REST API for invoice creation. Draft me the endpoint.

Important constraints for this project:
- We always use Prisma ORM, never Drizzle.
- One Prisma schema file per domain — don't merge them.
- The team uses the prisma-client-js generator with output to ./generated/client.

Reply with the endpoint code plus a short summary of these decisions so I can
confirm we're aligned.
PROMPT

echo
echo "Session A complete. The Stop hook should have distilled the conversation."
echo "Inspect ~/.claude/hooks/memanto/logs/distill_session.log to confirm."
echo "Then run ./run_session_b.sh in a NEW terminal."
