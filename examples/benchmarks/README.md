# The Great Agentic Memory Showdown: Memanto vs Mem0

> **Benchmark**: Scenario B — Shifting Persona & Temporal Tracking Test  
> **Hypothesis**: Memanto's direct-upsert architecture delivers lower token overhead and better current-preference recall than Mem0's LLM-extraction pipeline.

---

## What This Measures

When an AI assistant's user **changes their mind** across sessions, can the memory system correctly surface the *current* preference without being polluted by stale history?

This benchmark stress-tests that exact production scenario using a 5-session evolving persona, then scores both systems on:

| Metric | Description |
|--------|-------------|
| **Total tokens written** | Tokens consumed during memory ingestion |
| **Total tokens retrieved** | Tokens returned across all evaluation queries |
| **p95 write latency** | 95th-percentile storage latency (seconds) |
| **p95 read latency** | 95th-percentile retrieval latency (seconds) |
| **Accuracy score** | LLM-as-judge 0–3 scale per query, averaged across 5 queries |

---

## Dataset: "The Evolving Film Enthusiast"

A user's movie preferences evolve through 5 distinct sessions:

| Session | Label | Preference |
|---------|-------|-----------|
| 1 | Action-lover baseline | John Wick, The Dark Knight, fast-paced films |
| 2 | Shifting toward sci-fi | Dune, Interstellar, wants films that make them think |
| 3 | Documentary phase | Planet Earth II, The Social Dilemma |
| 4 | **Rejection of documentaries** | "Too slow and preachy", switches to psychological thrillers |
| 5 | **Horror phase (current)** | Hereditary, Midsommar, Ari Aster |

**5 evaluation queries** test the system's temporal tracking:
- Q1: What is the user's **current** preference? (must say Horror, not Action or Sci-Fi)
- Q2: What was the **first** stated preference? (Action)
- Q3: Did the user **ever** like documentaries? (Yes — must not be lost)
- Q4: Which specific films and directors were mentioned? (breadth recall)
- Q5: Applied recommendation — what should I suggest? (Horror films)

---

## Architecture Under Test

### Memanto (via `moorcheh-sdk`)

```
User message → MoorchehClient.documents.upsert() → Moorcheh serverless index
                         ↑
             No LLM extraction — zero inference overhead at write time
```

- **Write cost**: Only the document text itself (no LLM calls)
- **Read cost**: Semantic search on Moorcheh's index — returns relevant snippets
- **Temporal tracking**: Relies on recency-weighted retrieval and tags

### Mem0 (via `mem0ai` v2.0.4)

```
User messages → Mem0 extraction LLM (Claude Haiku) → Vectorized memory facts
                         ↑
          Calls the LLM to extract, deduplicate, and update memory entities
```

- **Write cost**: Document text + LLM inference for extraction/deduplication
- **Read cost**: Semantic search over extracted memory entities
- **Temporal tracking**: LLM-based conflict resolution between contradictory memories

---

## Environment Setup

```bash
# 1. Clone and enter the directory
cd examples/benchmarks/

# 2. Install dependencies
pip install -r requirements.txt
# NOTE: First run downloads sentence-transformers model (~90MB) for Mem0 embeddings

# 3. Configure environment variables
cp .env.example .env
# Edit .env: set MOORCHEH_API_KEY and ANTHROPIC_API_KEY

# 4. Run the benchmark
source .env   # or: export MOORCHEH_API_KEY=... ANTHROPIC_API_KEY=...
python3 run_benchmark.py
```

### Quick run (Memanto only, no HuggingFace download)

```bash
python3 run_benchmark.py --skip-mem0
```

### Without accuracy judge (no Anthropic API cost)

```bash
python3 run_benchmark.py --skip-judge
```

---

## System Configuration

| Parameter | Value |
|-----------|-------|
| **Memanto SDK** | `moorcheh-sdk>=1.3.5` via `MoorchehClient.documents.upsert()` |
| **Mem0 version** | `mem0ai>=2.0.0` |
| **Mem0 LLM backend** | `claude-haiku-4-5-20251001` (Anthropic) |
| **Mem0 embedder** | `multi-qa-MiniLM-L6-cos-v1` (HuggingFace, local) |
| **Mem0 vector store** | Qdrant in-memory (no external service) |
| **LLM-as-judge model** | `claude-haiku-4-5-20251001` |
| **Token counter** | `tiktoken` `cl100k_base` encoding |
| **Dataset** | 5 sessions × ~3 messages, 5 evaluation queries |
| **Prompt structure** | Raw user messages; no system prompt augmentation during ingestion |

---

## Isolated Variables

To ensure scientific comparability:

1. **Same dataset** — both systems process the identical 15 messages and 5 queries
2. **Same judge** — Claude Haiku evaluates both systems' outputs using the same rubric
3. **Same judge prompt** — hardcoded in `metrics/accuracy_judge.py`, not tuned per system
4. **Isolated namespaces** — each benchmark run uses a fresh UUID-namespaced Memanto collection and a new Mem0 user ID
5. **Same top-k** — both systems retrieve `top_k=5` results per query
6. **Token counting** — tiktoken `cl100k_base` applied to raw text for both systems

**Not controlled** (by design): Mem0's internal LLM extraction prompt is the system default. This is intentional — the benchmark measures real-world out-of-the-box performance, not artificially constrained configurations.

---

## Expected Output

```
🏆 The Great Agentic Memory Showdown
   Scenario B: Shifting Persona & Temporal Tracking Test
   Dataset: 5 sessions, 5 evaluation queries
   Judge: Claude Haiku (LLM-as-judge, score 0-3 per query)
   Comparison: Memanto (moorcheh-sdk) vs Mem0 (mem0ai v2.0.4)

──────────────────────────────────────────────────────────────────────
  MEMANTO — Ingestion Phase
──────────────────────────────────────────────────────────────────────
  [session_1] Action-lover baseline              tokens_written= 107  latency=0.412s
  [session_2] Shifting toward sci-fi             tokens_written=  96  latency=0.388s
  ...

──────────────────────────────────────────────────────────────────────
  BENCHMARK RESULTS — HEAD-TO-HEAD COMPARISON
──────────────────────────────────────────────────────────────────────
  Metric                                        Memanto       Mem0    Winner
  ──────────────────────────────────────────────────────────────────────────
  Total tokens written (ingestion)                 520        1840  Memanto ✓
  Total tokens retrieved (all queries)             185         210  Memanto ✓
  p95 write latency (s)                          0.512       3.241  Memanto ✓
  p95 read latency (s)                           0.089       0.124  Memanto ✓
  Avg accuracy score (0-3)                        2.60        1.80  Memanto ✓

  Token footprint delta:  Memanto uses +71.7% fewer tokens than Mem0
  Write latency delta:    Memanto is 6.3x faster on p95 writes
```

Results are saved as JSON to `results/benchmark_<timestamp>.json` for reproducibility.

---

## File Structure

```text
examples/benchmarks/
├── README.md                         ← This file
├── requirements.txt                  ← All dependencies with pinned minimums
├── .env.example                      ← Environment variable template
├── run_benchmark.py                  ← Main benchmark runner
├── dataset.py                        ← Shifting persona dataset + golden answers
├── adapters/
│   ├── __init__.py
│   ├── memanto_adapter.py            ← Memanto via moorcheh-sdk
│   └── mem0_adapter.py               ← Mem0 via mem0ai (local config)
├── metrics/
│   ├── __init__.py
│   ├── token_counter.py              ← tiktoken-based token counting
│   └── accuracy_judge.py             ← Claude Haiku LLM-as-judge
└── results/
    └── .gitkeep                      ← Output directory for JSON results
```

---

## Interpreting Results

**Accuracy score rubric** (applied by Claude Haiku judge):
- `3` = Correct and complete — directly answers the query consistent with golden answer
- `2` = Partially correct — mostly right with minor gaps
- `1` = Wrong/stale — retrieved data but contains contradictory or outdated information
- `0` = No useful information — empty or irrelevant retrieval

**Key insight**: The hardest test is Q1 ("What is the user's current preference?"). A system that returns *all* history without temporal weighting will surface "action movies" and "sci-fi" alongside "horror" — scoring 1 or 2. A system that correctly identifies recency should score 3.

---

## Acknowledgements

Built for the [Memanto Benchmarking & Evaluation Challenge](https://github.com/moorcheh-ai/memanto/issues/639).
