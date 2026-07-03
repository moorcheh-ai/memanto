# Bounty #639: Memanto Benchmarking Challenge

## Summary

This submission adds a reproducible benchmark suite for the Great Agentic Memory
Showdown. The suite compares Memanto-style typed, temporal recall against another
agent memory framework on the challenge's required axis: **retrieval accuracy vs.
resource footprint**.

The implementation is intentionally split into two paths:

1. **Offline smoke benchmark** (`memanto-offline` vs. `lexical-baseline`) for CI,
   contributors, and reviewers without API keys.
2. **Live benchmark adapters** (`memanto-rest` and `mem0`) for real Memanto vs.
   Mem0 runs using the same dataset, scoring code, and resource accounting.

## Files

- `scripts/memanto_memory_benchmark.py` — benchmark runner, adapters, scoring,
  token estimates, p95 latency reporting, JSON/Markdown output.
- `examples/benchmarks/agent_memory_showdown/dataset.json` — source evaluation
  dataset with evolving preferences, dense operational facts, and noisy incident
  context.
- `examples/benchmarks/agent_memory_showdown/requirements.txt` — optional live
  adapter dependencies.
- `tests/test_memory_benchmark.py` — unit tests covering dataset loading,
  scoring, resource metrics, and CLI output.

## Benchmark design

The dataset stresses production memory behavior that commonly hurts stateful
agents:

- **Dynamic preference resolution:** an old Python indentation preference is
  superseded by a newer preference. Correct systems should retrieve the current
  preference and avoid stale context.
- **Dense operational recall:** production cluster, latency SLO, security owner,
  and incident root cause facts are mixed with noisy deploy-log content.
- **Resource accounting:** the runner records estimated tokens ingested,
  estimated tokens retrieved, average retrieved tokens per question, p95 ingest
  latency, and p95 recall latency.

Accuracy is deterministic golden-set matching:

- Each question defines `expected_terms`.
- Some questions define `forbidden_terms` for stale or contradictory recall.
- Question score is expected-term recall minus forbidden-term penalty, clipped at
  zero.
- Framework accuracy is the mean score across all questions.

The token estimate uses a dependency-free `ceil(chars / 4)` approximation so the
benchmark can run anywhere. Teams that want exact tokenizer accounting can add a
custom post-processing step without changing the dataset.

## Quick offline run

From the repository root:

```bash
python scripts/memanto_memory_benchmark.py \
  --frameworks memanto-offline,lexical-baseline \
  --dataset examples/benchmarks/agent_memory_showdown/dataset.json \
  --output benchmark-results.json
```

Markdown output for reports:

```bash
python scripts/memanto_memory_benchmark.py \
  --frameworks memanto-offline,lexical-baseline \
  --format markdown \
  --output benchmark-results.md
```

## Live Memanto vs. Mem0 run

Install optional dependencies in an isolated environment:

```bash
python -m venv .benchmark-venv
source .benchmark-venv/bin/activate
python -m pip install -e .
python -m pip install -r examples/benchmarks/agent_memory_showdown/requirements.txt
```

Start Memanto and create/activate a throwaway benchmark agent. Export the active
agent and session values:

```bash
memanto serve
# In another shell, create/activate an agent by CLI or API, then export:
export MEMANTO_BASE_URL="http://localhost:8000"
export MEMANTO_AGENT_ID="benchmark-639"
export MEMANTO_SESSION_TOKEN="<session token>"
```

Configure Mem0 according to your chosen backend. For example, set OpenAI and an
optional Mem0 config JSON:

```bash
export OPENAI_API_KEY="<openai key>"
# Optional: either raw JSON or a path to a JSON config file.
export MEM0_CONFIG_JSON='{"llm":{"provider":"openai","config":{"model":"gpt-4o-mini"}}}'
```

Run both live adapters against the same dataset:

```bash
python scripts/memanto_memory_benchmark.py \
  --frameworks memanto-rest,mem0 \
  --dataset examples/benchmarks/agent_memory_showdown/dataset.json \
  --output memanto-vs-mem0-results.json
```

## Interpreting results

The JSON report contains one entry per framework:

```json
{
  "framework": "memanto-offline",
  "accuracy": 1.0,
  "resource_footprint": {
    "estimated_tokens_ingested": 185,
    "estimated_tokens_retrieved": 152,
    "avg_retrieved_tokens_per_query": 30.4,
    "p95_ingest_latency_ms": 0.01,
    "p95_recall_latency_ms": 0.05
  }
}
```

Use this matrix for Challenge #639:

| Metric | Why it matters |
| --- | --- |
| `accuracy` | Golden answer coverage and stale-memory avoidance. |
| `estimated_tokens_ingested` | Approximate write-side context/API cost. |
| `estimated_tokens_retrieved` | Approximate downstream context-window footprint. |
| `p95_ingest_latency_ms` | Tail write latency. |
| `p95_recall_latency_ms` | Tail retrieval latency. |

## Reproducibility notes

- The default CI path has no network calls and no third-party dependencies.
- Live adapters are opt-in and fail fast with clear environment-variable errors.
- The same scoring function is used for offline and live frameworks.
- The source dataset is versioned in the repository so future submissions can add
  larger fixtures without changing the benchmark contract.
