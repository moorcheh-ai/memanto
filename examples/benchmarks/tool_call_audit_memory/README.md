# Tool-Call Audit Memory Benchmark

This example is a submission for issue #639, "The Great Agentic Memory Showdown."

It benchmarks a failure mode that appears in long-running coding agents: the model has to remember user constraints, review feedback, current test commands, feature-flag renames, payout state, and secret-handling rules while its raw tool-call transcript keeps growing. A naive append-only log has plenty of recall but injects stale decisions and secret-shaped values. A recent-window log is cheap but forgets older durable constraints. The active digest acts like a Memanto companion: it stores typed current facts, supersedes stale keys, redacts secrets, and injects only relevant evidence.

## What It Measures

- Retrieval accuracy across current engineering facts.
- Average retrieved token footprint.
- p95 retrieval latency.
- Stale conflict rate.
- Secret leak rate.

## Run

```bash
python examples/benchmarks/tool_call_audit_memory/run_benchmark.py
```

Generate sample reports:

```bash
python examples/benchmarks/tool_call_audit_memory/run_benchmark.py \
  --output examples/benchmarks/tool_call_audit_memory/results/sample_results.json \
  --markdown examples/benchmarks/tool_call_audit_memory/results/sample_results.md
```

Run tests:

```bash
python -m unittest examples.benchmarks.tool_call_audit_memory.test_benchmark -q
```

## Backends Compared

| Backend | Description |
| --- | --- |
| `append_only_log` | Stores every audit event and retrieves matching raw text. It recalls facts but also surfaces stale decisions and secrets. |
| `windowed_recent_log` | Only retrieves recent audit text. It is compact but loses older durable constraints. |
| `active_audit_digest` | Keeps one current fact per memory key, redacts secret-shaped values, and retrieves typed facts by question relevance. |

## Why This Is Useful

The benchmark focuses on a production coding-agent behavior that raw vector or graph dumps often handle poorly: operational memory needs to be current, compact, scoped, and safe. The same query may need a newer feature flag while suppressing the stale flag, or a payment-state fact while avoiding sensitive payout details. The active digest demonstrates how a memory companion can win on accuracy and safety while reducing context tokens.
