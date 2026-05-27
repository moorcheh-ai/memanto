# Demo Transcript

## Session A: `/grill-with-docs`

Prompt:

```text
Review the payment service architecture and identify the rules the next coding
skill should follow.
```

Skill output summary:

```text
Decision: Use FastAPI routers for HTTP boundaries.
Preference: Write pytest coverage before changing shared behavior.
Instruction: Keep service functions pure unless persistence is required.
```

The `post` lifecycle step extracts the three typed lines above and stores them
in the Memanto skill memory backend.

## Session B: `/tdd`

Prompt:

```text
Implement the invoice endpoint after the architecture review.
```

The `pre` lifecycle step recalls the stored architecture decisions and renders
them into the skill prompt as a compact context block. The `/tdd` skill starts
with the payment-service decisions available even though it is a separate skill
run.

## Wrapped Command Mode

The same flow can be collapsed into one non-invasive wrapper call:

```bash
python memanto_skills_memory.py run \
  --skill tdd \
  --prompt "Implement the invoice endpoint after the architecture review." \
  --tags payments,tdd \
  -- \
  claude /tdd "Implement the invoice endpoint"
```

Before launching `claude`, the wrapper sets `MEMANTO_SKILL_CONTEXT` with the
recalled decisions. After `claude` exits, any explicit `Decision:`,
`Preference:`, or `Instruction:` lines in the output are saved for the next
skill invocation.
