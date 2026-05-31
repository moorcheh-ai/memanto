# Demo transcript

This transcript is designed for a short screen recording.

## Run 1 — architecture decision is captured

```bash
python skill_memory_hook.py post \
  --skill "/spec" \
  --summary "Decision: use hexagonal architecture for billing. Convention: domain tests live beside billing fixtures. Preference: keep generated review comments short." \
  --dry-run
```

Expected output shows three `memanto remember` calls: one decision, one convention, and one preference.

## Run 2 — a different skill recalls the decision

```bash
python skill_memory_hook.py pre \
  --task "/tdd implement invoice overdue fee" \
  --files "src/billing/invoice.py,tests/test_invoice.py" \
  --dry-run
```

Expected output shows the `MEMANTO_CONTEXT` block that a skills runner would inject into the next prompt.

## Why this proves cross-session memory

The two commands are intentionally independent. The second command does not receive the first command's summary directly; it asks Memanto for the relevant project memory and injects the compact result before the new skill starts.
