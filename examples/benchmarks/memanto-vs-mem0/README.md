# Memanto vs Mem0 — The Executive Shadow Benchmark

> *A rigorous, reproducible benchmark that stress-tests AI memory systems on the hardest problem in production agents: contradiction resolution and temporal preference drift.*

## The Scenario

**The Executive Shadow** — a personal AI assistant tracking a startup founder across 6 months of real-world complexity:

- **46 conversation turns** across 6 monthly sessions
- **7 explicit contradictions** — decisions that are made and then reversed (fundraising strategy, Workday integration, market focus, office policy, communication style, SaaS spending rules)
- **Dense, mixed-domain context** — product, finance, hiring, personal preferences, investor relationships all interleaved
- **8 evaluation queries** crafted to expose the exact failure modes of flat vector stores

The core thesis: **a flat vector store retrieves by semantic similarity, not recency or conflict resolution.** When a founder says "we're raising from Sequoia" in Month 1 and "we're dropping Sequoia" in Month 4, a flat store returns both — and the agent is confused. Memanto's typed memories and conflict detection should surface the current state cleanly.

## Architecture

```text
executive_shadow.json          ← deterministic golden dataset
        ↓
harness.py                     ← drives both systems identically
  ├── MemantoAdapter            ← Memanto SDK (create/activate/remember/recall)
  └── Mem0Adapter               ← Mem0 Platform SDK (add/search)
        ↓
evaluator.py (LLMJudge)        ← OpenRouter LLM scores each answer 0–15
        ↓
reporter.py                    ← terminal table + results/benchmark_*.json
        ↓
dashboard.py                   ← Streamlit visualisation
```

## Metrics

| Metric | What it measures |
|--------|-----------------|
| **Total tokens ingested** | How much context each system needs to store 6 sessions |
| **Total tokens recalled** | How much context is returned per query (bloat = noise) |
| **p95 ingest latency** | 95th-percentile time to store one session |
| **p95 recall latency** | 95th-percentile time to answer one query |
| **Accuracy (0–5)** | Does the answer match the golden answer? |
| **Staleness avoidance (0–5)** | Does it avoid contradicted older facts? |
| **Precision (0–5)** | Is the answer focused, or polluted with noise? |

**Max eval score:** 120 (8 queries × 15 points each)

## Evaluation Query Types

| Type | What it tests | Example |
|------|--------------|---------|
| `contradiction_resolution` | Must surface current decision over earlier one | "Is Workday being built?" — was dropped in Month 2, reinstated in Month 5 |
| `staleness_detection` | Must deprioritise superseded preferences | "How should I format messages?" — rule changed in Month 6 |
| `recency` | Must return latest state, not historical average | "What is current team size and burn?" |

## Quick Start

### 1. Install

```bash
cd examples/benchmarks/memanto-vs-mem0
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Fill in MOORCHEH_API_KEY, MEM0_API_KEY, OPENROUTER_API_KEY
```

### 3. Run the benchmark

```bash
# Full run with LLM judge (~3–5 minutes)
python run_benchmark.py

# Metrics only (no LLM judge, ~1 minute)
python run_benchmark.py --skip-judge

# Custom judge model
python run_benchmark.py --judge-model openai/gpt-4o-mini
```

### 4. View results

```bash
# Terminal report (printed automatically after each run)

# Streamlit dashboard
streamlit run dashboard.py
```

## Experimental Controls

All variables held constant between the two systems:

| Variable | Value |
|---------|-------|
| Input dataset | Identical — `executive_shadow.json` |
| Session order | Sequential sessions 1–6 |
| Query set | 8 identical evaluation queries |
| Recall limit | 10 memories per query (both systems) |
| Judge LLM | `openai/gpt-4o-mini` via OpenRouter |
| Judge temperature | 0.0 |
| Judge seed | 42 (`gpt-4o-mini` honours this natively via OpenRouter) |
| Judge prompt | Identical system prompt for both systems |
| Timing | `time.perf_counter()` wall time per operation |
| Token counting | Character-based estimate (len/4) applied identically to both |
| Memanto agent pattern | `tool` |
| Indexing wait | Mem0: polled via `get_all` until memories visible (max 60s, 4s interval); Memanto: 3s fixed wait |
| Session pause | 0.5s between sessions to respect rate limits |

### Token methodology note

Mem0 Platform runs an LLM extraction pass on every `add()` call to extract and deduplicate memories. This is an internal, async process — token cost is not exposed by the API. The benchmark captures wall-clock ingestion latency as a proxy for this overhead. Memanto stores memories directly with no ingestion-time LLM call; its LLM cost appears only at recall time.

### Conflict resolution note

Memanto's conflict resolution is human-in-the-loop: it flags contradictory memories and surfaces them to the user, who decides which to keep. It does not auto-resolve conflicts at recall time. The `contradiction_resolution` queries therefore measure whether the system returns the *most recent* relevant memories, not whether it has merged conflicting facts. A lower staleness score reflects semantic retrieval returning both old and new memories simultaneously, not a resolution failure.

### Variance

Three runs were conducted using `anthropic/claude-3-5-haiku` as judge. Memanto won 2/3 runs; average scores were Memanto 55.0% vs Mem0 43.6%. The default judge is now `openai/gpt-4o-mini` which honours `seed=42` natively, providing better reproducibility for future runs. Mem0's ingestion quality also varies between runs (async LLM extraction), which affects what gets stored and therefore what scores are achievable.

## Environment

| Requirement | Version |
|------------|---------|
| Python | 3.10+ |
| memanto | ≥0.1.0 |
| mem0ai | ≥2.0.5 |
| openai | ≥1.30.0 (OpenRouter-compatible) |

## Project Structure

```text
memanto-vs-mem0/
├── data/
│   └── executive_shadow.json    # Scenario dataset + golden answers
├── adapters/
│   ├── __init__.py
│   ├── base.py                  # MemoryAdapter interface
│   ├── memanto_adapter.py       # Memanto implementation
│   └── mem0_adapter.py          # Mem0 implementation
├── evaluator.py                 # LLM-as-judge
├── harness.py                   # Benchmark orchestrator
├── reporter.py                  # Terminal + JSON output
├── run_benchmark.py             # CLI entry point
├── dashboard.py                 # Streamlit visualisation
├── requirements.txt
├── .env.example
└── results/                     # Auto-created, holds JSON run outputs
```

---

## Social Posts

- X: [add after publishing]
- Reddit (r/AgenticMemory): [add after publishing]
