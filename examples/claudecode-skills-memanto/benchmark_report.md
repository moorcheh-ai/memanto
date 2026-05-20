# Productivity Benchmark Report

Command:

```bash
python examples/claudecode-skills-memanto/productivity_benchmark.py
```

Credential-free result:

```json
{
  "baseline_repeated_instructions": 6,
  "memanto_injected_constraints": 6,
  "recalled_context_contains": {
    "authentication middleware stateless": true,
    "avoid global mutable caches": true,
    "tenant lookup into a small dependency": true
  },
  "repeated_instruction_reduction_pct": 100.0,
  "skill_sequence": [
    "/grill-with-docs",
    "/tdd",
    "/handoff"
  ]
}
```

Interpretation:

- Baseline flow requires six repeated architecture/style instructions across later skill runs.
- Memanto recall injects those six constraints before downstream skill runs.
- The demo avoids all repeated instructions in the three-skill sequence, reporting a 100% repeated-instruction reduction.
