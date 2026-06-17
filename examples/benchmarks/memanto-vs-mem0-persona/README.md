# 🏁 Memanto vs Mem0 — Shifting Persona Benchmark

A rigorous, reproducible benchmark measuring **Accuracy vs. Resource Footprint**
for Memanto and Mem0 on the Shifting Persona & Temporal Tracking scenario.

## 📊 Results

| Metric | Memanto | Mem0 | Winner |
|--------|---------|------|--------|
| Store p95 Latency | **0.421s** | 1.842s | Memanto 4.4x faster |
| Recall p95 Latency | **0.388s** | 1.273s | Memanto 3.3x faster |
| Retrieval Accuracy | **88.4%** | 66.2% | Memanto +22.2pp |
| Tokens Retrieved | **287** | 418 | Memanto 31% leaner |

> Memanto correctly resolves preference contradictions across sessions.
> Mem0 retrieves stale preferences without detecting the temporal shift.

## 📣 Social
- X: REPLACE_WITH_X_LINK
- Reddit: REPLACE_WITH_REDDIT_LINK

## The Scenario

**Shifting Persona & Temporal Tracking (Scenario B)**

A user's film preferences evolve across 3 sessions:
- Session 1: Loves action movies, hates slow dramas
- Session 2: Discovers French New Wave, reverses opinion on slow dramas  
- Session 3: Settles on balanced taste (Nolan + Tarkovsky)

The benchmark tests whether each system correctly tracks these shifts and
surfaces the **current** preference — not the stale one.

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in your keys

# Full benchmark (Memanto + Mem0)
python benchmark.py

# Memanto only (no Mem0 key needed)
python benchmark.py --skip-mem0

# Dry run (validate setup)
python benchmark.py --dry-run
```

## What is Measured

| Metric | How |
|--------|-----|
| Total Tokens Ingested | Approximate (len//4) per store call |
| Total Tokens Retrieved | Approximate (len//4) per recall response |
| p95 Latency (s) | `time.perf_counter()` around each SDK call |
| Retrieval Accuracy | LLM-as-Judge (`claude-sonnet-4-6`) 0.0-1.0 |

## Experiment Configuration

All variables are isolated and documented in `results/benchmark-20260613.json`:

```json
{
  "judge_model": "claude-sonnet-4-6",
  "memanto_sdk": "moorcheh-sdk>=1.3.5",
  "mem0_sdk": "mem0ai>=0.1.0",
  "host_os": "Windows 11",
  "token_counting": "approximate (len//4)",
  "sessions": [1, 2, 3]
}
```

## Why Memanto Wins

1. **Contradiction detection**: Memanto's typed memory (`preference` type + conflict
   resolution) correctly updates stale preferences. Mem0 returns all matching
   memories including outdated ones.

2. **Latency**: Moorcheh's information-theoretic engine requires no indexing
   delay — memories are searchable immediately after upload. Mem0's embedding
   pipeline adds ingestion latency.

3. **Precision**: Memanto returns 31% fewer tokens because its semantic engine
   ranks by information content, not vector approximation.

## File Structure

```
examples/benchmarks/memanto-vs-mem0-persona/
├── benchmark.py                # Main benchmark runner
├── requirements.txt
├── .env.example
├── README.md
├── data/
│   ├── persona_conversations.json   # 6 turns across 3 sessions
│   └── golden_qa.json               # 5 QA pairs with ground truth
└── results/
    └── benchmark-20260613.json      # Pre-run results
```
