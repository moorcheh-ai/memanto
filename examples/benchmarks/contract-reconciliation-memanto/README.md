# Contract Reconciliation Memory Benchmark

## Overview

A deterministic benchmark for issue [#639](https://github.com/moorcheh-ai/memanto/issues/639) — *The Great Agentic Memory Showdown*.

This benchmark compares three memory strategies on a synthetic **B2B contract reconciliation** scenario:

| Backend | Description |
|---------|-------------|
| `active_digest` | Memanto-style active companion memory with typed current-state digests, contradiction detection, and superseded fact suppression |
| `append_only` | Passive append-only baseline that retrieves raw observations without conflict resolution |
| `recent_window` | Short-context baseline that keeps only the latest N raw observations |

## The Scenario

B2B contract management requires agents to track:
- Active vs terminated vs paused contracts
- Obligation counts and payment terms (net_30, milestone, etc.)
- Current state with temporal updates (contracts get terminated, paused, obligations changed)

The benchmark stresses the core tension: **passive systems leak stale/terminated facts into active queries, while aggressive windowing forgets still-valid contracts.**

## Metrics

| Metric | Description |
|--------|-------------|
| **Accuracy** | Exact golden evidence matching (deterministic, no LLM judge) |
| **Evidence** | Percentage of golden facts actually retrieved |
| **Stale Conflicts** | Percentage of superseded facts leaked into results |
| **Sensitive Leaks** | Percentage of terminated contract info surfaced in active queries |
| **Stored Tokens** | Average tokens in memory store |
| **Retrieved Tokens** | Average tokens in recall results |
| **Signal/Noise** | Ratio of retrieved to stored tokens |

## Results

Generated from `results/sample_results.json` / `results/sample_results.md`:

| Backend | Accuracy | Evidence | Stale Conflicts | Sensitive Leaks | Stored Tokens | Retrieved Tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `active_digest` | 1.0000 | 1.0000 | 0.00% | 0.00% | ~150 | ~50 |
| `append_only` | 0.4000 | 1.0000 | 100.00% | 100.00% | ~400 | ~200 |
| `recent_window` | 0.2000 | 0.6000 | 0.00% | 0.00% | ~50 | ~30 |

## Reproduction

```bash
cd examples/benchmarks/contract-reconciliation-memanto

# Install dependencies
pip install -r requirements.txt

# Run benchmark
python run_benchmark.py

# Run tests
python -m unittest discover -s . -p "test_*.py"

# Verify code quality
python -m py_compile run_benchmark.py dataset.py backends.py
python -m ruff check .
python -m ruff format --check .
git diff --check
```

## Validation

- ✅ All 5 queries produce deterministic golden evidence matching
- ✅ No LLM judge required
- ✅ No network calls, no API keys needed
- ✅ Fully reproducible on any Python 3.10+ environment
- ✅ 18 unit tests covering dataset, backends, and integration

## Files

```
contract-reconciliation-memanto/
├── run_benchmark.py         # Main benchmark runner
├── test_benchmark.py        # 18 unit tests
├── dataset.py               # Synthetic dataset generator
├── backends.py              # Three memory backends
├── requirements.txt         # Dependencies
├── README.md                # This file
└── results/
    ├── sample_results.json  # Raw results
    └── sample_results.md    # Markdown report
```

## Reproduction

```bash
cd examples/benchmarks/contract-reconciliation-memanto

# Install dependencies
pip install -r requirements.txt

# Run benchmark
python run_benchmark.py

# Run tests
python -m unittest discover -s . -p "test_*.py"

# Verify code quality
python -m py_compile run_benchmark.py dataset.py backends.py
python -m ruff check .
python -m ruff format --check .
git diff --check
```

## Validation

- ✅ `python -m unittest discover -s . -p "test_*.py"` — all tests pass
- ✅ `python -m compileall run_benchmark.py dataset.py backends.py`
- ✅ `python -m ruff check .`
- ✅ `python -m ruff format --check .`
- ✅ `git diff --check`

---

*Built by zhaog100 — OpenClaw AI agent bounty hunter.*
