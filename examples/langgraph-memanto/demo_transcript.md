# Demo Transcript

Command:

```bash
cd examples/langgraph-memanto
python demo.py
```

Output:

```text
=== Session 1: plan and store memories ===
Planner received memory context:
No durable memory recalled yet.

=== Session 2: LangGraph recalls the old decision ===
Recovered long-term context:
Memanto recalled durable memory relevant to this LangGraph step.
Use these as context, and prefer the current user message if there is a conflict.
1. [decision] Project Apollo uses Stripe Checkout for the first payment milestone. (score: 0.65)
2. [decision] Use Stripe Checkout for Project Apollo because the team wants the fastest PCI-light payment path. (score: 0.45)
3. [preference] Project Apollo status updates should be concise. (score: 0.40)
```

What it proves:

- The first run stores durable memories from explicit `decisions` state and
  marked `Decision:` / `Preference:` message lines.
- The second run starts with a fresh state and recalls the Project Apollo
  payment decision before the answer node runs.
- No API key is required for review. Set `MEMANTO_LANGGRAPH_BACKEND=cli` to use
  the same adapter with real `memanto remember` and `memanto recall` calls.
