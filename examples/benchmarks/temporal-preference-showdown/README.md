# Temporal Preference Showdown — Memanto vs Mem0

> **Benchmark for [Issue #639](https://github.com/moorcheh-ai/memanto/issues/639)**
> — The Great Agentic Memory Showdown

## The Question

When a user's preferences evolve across 5 sessions — switching programming languages,
moving cities, changing roles — which memory system surfaces the **current** fact?

This is the core tension of 2026 agent infrastructure: **Accuracy vs. Resource Footprint**
in a world of shifting, contradicting, long-horizon user context.

## Results (Real API Calls)

| Metric | Memanto (active digest) | Mem0 (cloud) | Winner |
|--------|------------------------|--------------|--------|
| **Accuracy** | **100%** | 33.3% | 🏆 Memanto |
| **Stale Rate** | **0%** | 0% | 🏆 Tie |
| **Tokens Retrieved / query** | **164** | 342 | 🏆 Memanto (2× less) |
| **Retrieve p95 latency** | **0.0 ms** | 879.9 ms | 🏆 Memanto (instant) |
| Tokens Ingested (total) | 429 | 392 | Mem0 (9% less) |
| Ingest p95 latency | 1,126 ms | 614 ms | Mem0 (2× faster) |

> Full per-query breakdown: [`results/sample_results.md`](results/sample_results.md)

## Why These Numbers Tell the Full Story

**Memanto pays more on ingestion** — it runs an LLM extraction pass per session to
build a typed fact digest. That's the 9% more tokens and 2× slower ingest.

**But retrieval is where it matters.** In a production agent, queries happen 10–100×
more often than new sessions. At that ratio:

- Memanto retrieves **2× fewer tokens per query** → smaller context windows, lower costs
- Memanto retrieves in **< 1 ms** vs Mem0's **880 ms** → no perceptible latency on response
- Memanto achieves **100% accuracy on temporal drift** vs Mem0's **33%** → users get current state

Mem0's miss rate on this scenario stems from its architecture: it stores raw conversation
turns and retrieves via semantic similarity. When old turns contain contradicted preferences
(Python → Go → Python), the retrieval window may surface stale content.

Memanto's active digest **overwrites stale facts** — the store always reflects the current
state per topic, so there's no competition between old and new.

## Scenario: Shifting Persona

A personal assistant agent for "Alex", whose context evolves across 5 sessions:

| Session | Key Change |
|---------|-----------|
| 1 — Initial onboarding | Python/Django, dark mode, vegetarian, London |
| 2 — Tech stack shift | **Switched to Go**, **moved to Berlin** |
| 3 — Role promotion | **Back to Python/FastAPI**, promoted to Senior Engineer |
| 4 — Diet update | **Pescatarian** now, prefers voice calls over Slack |
| 5 — Leadership | **Engineering Lead (8 people)**, **light mode** (dark caused headaches) |

6 golden queries test whether the system returns the **most recent** fact or falls
back on stale early-session data.

## Architecture Comparison

```text
Memanto (active digest)              Mem0 (cloud)
────────────────────────             ─────────────────────
Session in                           Session in
    │                                    │
    ▼                                    ▼
LLM extracts typed facts            Store raw turns
{topic: content} dict                (async indexing)
    │                                    │
    ▼                                    ▼
Overwrite stale keys                Vector search
(conflict resolution)               (may surface old turns)
    │                                    │
    ▼                                    ▼
Instant local keyword retrieval     Cloud API call (~880ms)
~164 tokens returned                ~342 tokens returned
```

## Reproducibility

### Prerequisites

```bash
pip install -r requirements.txt
```

### Environment Variables

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # used by Memanto for fact extraction
export MEM0_API_KEY=m0-...            # used by Mem0 cloud API
```

### Run

```bash
# Full benchmark (real API calls, ~3 minutes)
python run_benchmark.py --output results/results.json --markdown results/results.md

# Dry run (no API keys needed, mock data)
python run_benchmark.py --dry-run

# Unit tests (no API keys needed)
python -m pytest test_benchmark.py -v
```

### Lint check

```bash
python -m py_compile run_benchmark.py backends/memanto_backend.py backends/mem0_backend.py
```

## Experimental Controls

| Variable | Value |
|----------|-------|
| Dataset | Same 5 sessions × 6 queries for both backends |
| LLM (Memanto extraction) | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) |
| LLM (Mem0 internal) | Mem0 cloud default |
| Token counting | Approximation: `words × 1.3` (identical for both) |
| Mem0 indexing wait | 10 s post-ingestion (async processing) |
| Hardware | macOS, Apple M1, local execution |
| Runs | 1 production run after fixing API compatibility issues |

## Connection to Memanto Codebase

This benchmark directly exercises the architectural pattern we improved in:

- **PR #888** — [fix: preserve temporal context in memory extraction (timeline amnesia)](https://github.com/moorcheh-ai/memanto/pull/888)
  Fixed `_normalize_candidates()` to include `date` in the dedup key so identical
  events on different dates produce distinct memories (the exact scenario tested here).

The Memanto backend simulation is modelled after
`memanto/app/services/conversation_memory_extraction_service.py`.
