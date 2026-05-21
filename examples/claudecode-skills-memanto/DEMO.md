# Demo Transcript — Cross-Session Engineering Memory

This transcript demonstrates how the Memanto memory bridge persists engineering decisions across different Claude Code skill sessions.

## Setup

```bash
$ export MEMANTO_PREVIEW=1
$ export MEMANTO_AGENT=claude-code-skills
$ cd examples/claudecode-skills-memanto
```

## Session 1: Architecture Design with /grill-with-docs

```bash
$ bash skills-memory.sh wrap "/grill-with-docs 'Design the payment system'"

[memanto-bridge] === Pre-skill: Recalling engineering context ===
[memanto-bridge] [preview] No memories stored yet
[memanto-bridge] === Executing skill ===
/architecture decision: Use Stripe for payment processing with webhooks
/architecture decision: PostgreSQL for transaction storage with UUID primary keys
/architecture decision: All amounts stored in cents to avoid floating point issues
/architecture decision: Use idempotency keys for all payment requests

[memanto-bridge] === Post-skill: Distilling engineering decisions ===
[memanto-bridge] [preview] Memory stored locally (architecture)
[memanto-bridge] [preview] Memory stored locally (database)
[memanto-bridge] [preview] Memory stored locally (architecture)
[memanto-bridge] [preview] Memory stored locally (architecture)
[memanto-bridge] Engineering decisions stored for future sessions
```

## Session 2: Implementation with /tdd

```bash
$ bash skills-memory.sh recall "payment database"
[memanto-bridge] [preview] Searching memories for: payment database
  [2 matches] [database] PostgreSQL for transaction storage with UUID primary keys
  [1 matches] [architecture] All amounts stored in cents to avoid floating point issues
  [1 matches] [architecture] Use idempotency keys for all payment requests

$ /tdd "Implement the payment endpoints"
# → Automatically uses PostgreSQL + UUID + cents + idempotency keys
# → Zero repeated instructions needed!
```

## Session 3: Code Review with /handoff

```bash
$ bash skills-memory.sh recall "payment architecture"
[memanto-bridge] [preview] Searching memories for: payment architecture
  [2 matches] [architecture] Use Stripe for payment processing with webhooks
  [2 matches] [database] PostgreSQL for transaction storage with UUID primary keys
  [2 matches] [architecture] All amounts stored in cents to avoid floating point issues
  [2 matches] [architecture] Use idempotency keys for all payment requests

$ /handoff "Review the payment module for consistency"
# → Reviewer sees ALL past decisions and checks code against them
# → Catches a floating-point amount bug because memory says "cents only"
```

## Result: Zero Repeated Instructions

The developer never had to re-explain:
- Which payment provider to use
- What database schema applies
- How to handle monetary amounts
- Why idempotency keys matter

Memanto carried the engineering context across all three sessions automatically.
