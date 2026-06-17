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

To ensure scientific validity, all variables are held constant between the two systems:

| Variable | Value |
|---------|-------|
| Input dataset | Identical — `executive_shadow.json` |
| Session order | Identical — sessions 1–6 in sequence |
| Query set | Identical — 8 evaluation queries |
| Judge LLM | Same model, same prompt, same temperature (0.0) |
| Judge prompt | Identical system prompt for both systems |
| Timing methodology | `time.perf_counter()` wall time per operation |
| Token counting | Character-based estimate (len/4) for systems that don't expose token counts; applied identically to both |

## Environment

| Requirement | Version |
|------------|---------|
| Python | 3.10+ |
| memanto | ≥0.1.0 |
| mem0ai | ≥0.1.0 |
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
