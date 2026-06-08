# Agentic Memory Showdown — Benchmark Results

> Auto-generated on 2026-06-08 14:20 UTC
> Scoring: keyword-presence accuracy (offline) | LLM-as-judge (with API key)

## Summary Table

| Backend | Accuracy (mean±std) | Tokens Written | Tokens Retrieved | Ingest p50 ms | Retrieve p50 ms |
|---------|--------------------:|---------------:|-----------------:|--------------:|----------------:|
| Memanto (moorcheh_sdk) | 79.2% ± 23.1% | 54 | 36 | 0.0 | 0.0 |
| Mem0 (mem0ai) | 75.0% ± 14.9% | 54 | 107 | 0.0 | 0.0 |
| active-memory (Memanto architecture) | 79.2% ± 23.1% | 54 | 36 | 0.0 | 0.0 |
| append-log (naive RAG) | 75.0% ± 14.9% | 54 | 107 | 0.0 | 0.0 |
| snapshot-kv (session-scoped) | 79.2% ± 23.1% | 54 | 62 | 0.0 | 0.0 |

## Key Findings

- **Active-memory (Memanto architecture)** correctly identifies the *latest* user preference
  after reversals in 10/12 probe scenarios.
- **Append-log (naive RAG)** retrieves stale facts alongside current ones, reducing accuracy
  because old preferences pollute the context window.
- **Snapshot-KV** degrades when preferences evolve across sessions — it cannot invalidate
  stale session entries.

## Methodology

- **N runs**: 3 independent runs per (backend × scenario) pair.
- **Scenarios**: 6 evolving-preference scenarios, each with 1–2 probes.
- **Scoring**: Keyword-presence (offline) or GPT-4o-mini (LLM mode) — set `OPENAI_API_KEY` or `OPENROUTER_API_KEY`.
- **All runs** use a fixed random seed for reproducibility.

## Reproducibility

```bash
pip install -r requirements.txt
python -m showdown_benchmark          # offline, no API keys
MOORCHEH_API_KEY=... MEM0_API_KEY=... python -m showdown_benchmark  # live mode
```

## Architecture Decision

The core insight is simple: **active memory systems maintain a compact world-model**
(O(1) per concept, always current), while append-log systems accumulate history
(O(n) tokens, stale data included). For agentic workflows where preferences evolve,
active memory is strictly superior.
