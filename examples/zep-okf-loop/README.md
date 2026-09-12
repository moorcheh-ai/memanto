# Zep → Memanto → OKF

This showcase uses the new `memanto migrate zep` path. It does **not**
reimplement `memanto migrate` or OKF export. It adds a provider Memanto does
not already ship: Zep graph/fact dumps.

```bash
# 1. Map the sample dump (no API key, no writes)
memanto migrate zep --file examples/zep-okf-loop/zep_export.json --dry-run

# 2. Import into an activated agent
memanto migrate zep --file examples/zep-okf-loop/zep_export.json

# 3. Own it as portable OKF
memanto memory export --okf ./examples/zep-okf-loop/out-okf
```

Raw Zep chat turns are not imported as memories. Facts, graph edges, entity
node summaries, and session summaries are.
