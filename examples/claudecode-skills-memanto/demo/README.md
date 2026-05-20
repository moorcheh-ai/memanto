# Demo: cross-session memory in action

This directory contains a reproducible walkthrough that proves the integration
works — across separate terminal sessions, with no manual context-shoving.

## Files

| File | What it does |
|---|---|
| `verify_setup.py` | Checks hooks are installed, settings.json is wired, and the Moorcheh API key works. Run this first. |
| `run_session_a.sh` | Walks you through Session A — an architectural decision conversation. Records the expected output for comparison. |
| `run_session_b.sh` | Walks you through Session B in a fresh terminal — shows Claude recalling the prior decision. |
| `show_memories.sh` | Dumps every memory stored for this project (use as the bounty submission artifact). |

## Story

1. **Session A (Monday, 10am)**: You ask Claude to draft a REST endpoint for invoice creation. Claude proposes Drizzle ORM. You push back: your team standardized on Prisma, with the `prisma-client-js` generator and one schema file per domain. You and Claude land on that approach. Session ends.

2. **Session B (Monday, 4pm — new terminal, fresh memory)**: You ask Claude to write the integration test for the invoice endpoint. Without Memanto, Claude would propose Drizzle again (its default), and you'd repeat the explanation. **With Memanto**, Claude's response references Prisma and the single-schema-per-domain convention automatically.

3. **`show_memories.sh`** prints the stored memories that bridged the two sessions — typically:
   - `(preference) "use Prisma ORM, not Drizzle"`
   - `(decision) "one schema file per domain"`
   - `(context) "team uses prisma-client-js generator"`

## Running the demo

```bash
# 0. Confirm install
python3 verify_setup.py

# 1. Session A
./run_session_a.sh

# 2. Open a new terminal, cd back here

# 3. Session B (proves persistence)
./run_session_b.sh

# 4. Inspect what got remembered
./show_memories.sh
```

The first time, just read the script comments — they describe what to type into
Claude Code so you can replicate the conversation. Subsequent runs can use the
preset scripts to drive Claude headlessly via `claude -p`.
