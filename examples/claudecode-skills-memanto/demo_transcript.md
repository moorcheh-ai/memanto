# Demo Transcript

## Session A: `/grill-with-docs`

Input:

```text
Review the checkout flow before I implement tests.
```

Skill output:

```text
Decision: use server actions for checkout mutations.
Instruction: keep payment provider tokens out of browser code.
Preference: write one Playwright smoke test for the happy path.
```

Bridge result:

```text
stored_memories=3
```

## Session B: `/tdd`

Input:

```text
Add checkout coverage.
```

Injected context:

```text
MEMANTO_SKILL_CONTEXT:
- [decision] use server actions for checkout mutations (from /grill-with-docs: Review the checkout flow)
- [instruction] keep payment provider tokens out of browser code (from /grill-with-docs: Review the checkout flow)
- [preference] write one Playwright smoke test for the happy path (from /grill-with-docs: Review the checkout flow)
```

The second skill starts with the architecture and safety constraints already in
context, eliminating repeated manual prompting.
