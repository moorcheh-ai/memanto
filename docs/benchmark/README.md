# Memanto vs Mem0ai: Agentic Memory Benchmark

**Challenge**: [#639 [BOUNTY $100] 🐜 The Great Agentic Memory Showdown](https://github.com/moorcheh-ai/memanto/issues/639)

## Overview

A rigorous, reproducible benchmarking suite comparing **Memanto** against **Mem0ai** across two critical production scenarios:

| Scenario | Description | Key Metrics |
|----------|-------------|-------------|
| **A** — Context-Overhead & Latency Sprint | 25 dense technical log entries fed sequentially; measure memory bloat | Tokens/turn, p95 latency |
| **B** — Shifting Persona & Temporal Tracking | 3 sessions of user preference evolution with contradictions | Preference retention accuracy |

## How to Run

```bash
# 1. Install dependencies
pip install memanto mem0ai

# 2. Set API keys (Memanto only)
# Get your free key at https://console.moorcheh.ai
export MOORCHEH_API_KEY=mc_xxxxxxxxxxxx

# OR use on-prem mode
export MEMANTO_BACKEND=on-prem

# 3. Run
cd memanto_benchmark
python run_benchmark.py
```

## Architecture

```
memanto_benchmark/
├── run_benchmark.py     # Main benchmarking script
├── benchmark_results.json  # Output: structured metrics
└── README.md            # This file
```

## Methodology

### Scenario A: Context-Overhead & Latency Sprint

Feeds 25 realistic Kubernetes/cloud infrastructure log entries sequentially into both memory systems. Measures:

- **Tokens per ingestion** — how much context window each system consumes per entry
- **p95 retrieval latency** — how fast each system can search stored memories
- **Cumulative token growth** — does memory bloat over time?

### Scenario B: Shifting Persona & Temporal Tracking

Simulates a user whose preferences evolve over 3 sessions with explicit contradictions:

1. Session 1: "I love action movies", "I'm a night owl"
2. Session 2: "I'm into K-dramas now", "I wake up at 5am"
3. Session 3: "Marvel is formulaic", "Winter sports are the best"

Measures whether each system can:
- Track preference evolution over time
- Resolve contradictions correctly (latest preference wins)
- Avoid polluting context with stale information

## Environment

| Component | Version |
|-----------|---------|
| Memanto | 0.2.4 |
| Mem0ai | 2.0.10 |
| Python | 3.12.7 |
| OS | Windows 11 |

## Scoring Criteria (from Challenge)

| Criterion | Points |
|-----------|--------|
| Scientific rigor & reproducibility | 25 |
| Code quality | 20 |
| Results quality & insights | 20 |
| Documentation | 20 |
| Social amplification | 15 |
| **Total** | **100** |
