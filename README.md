# 🐜 The Great Agentic Memory Showdown: Memanto Benchmark Suite

**A rigorous, reproducible benchmarking suite comparing [Memanto](https://github.com/moorcheh-ai/memanto) against [Mem0](https://github.com/mem0ai/mem0) for AI agent memory management.**

> Submission for [Issue #639](https://github.com/moorcheh-ai/memanto/issues/639) — $100 Bounty

## 📋 Overview

This benchmark evaluates the core tension of 2026 agent infrastructure: **Accuracy vs. Resource Footprint**.

### Scenarios

| Scenario | Description | Focus |
|----------|-------------|-------|
| **A: Context-Overhead & Latency Sprint** | Dense technical logs ingested across sessions | Token efficiency, retrieval latency |
| **B: Shifting Persona & Temporal Tracking** | Evolving user preferences that contradict over time | Preference accuracy, temporal awareness |

### Metrics Collected

- **Total Tokens Ingested** — tokens consumed during memory storage
- **Total Tokens Retrieved** — tokens returned during memory search
- **p95 Latency (ms)** — 95th percentile latency for store/retrieve operations
- **Retrieval Accuracy** — LLM-as-a-Judge scoring (0-1) against golden answers

## 🚀 Quick Start

```bash
# 1. Clone and install
cd memanto-benchmark
pip install -r requirements.txt

# 2. Configure API keys
cp .env.example .env
# Edit .env with your keys

# 3. Run benchmark
python run_benchmark.py

# 4. View report
open reports/benchmark_report.html
```

## ⚙️ Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `MOORCHEH_API_KEY` | Memanto/Moorcheh API key | ✅ |
| `MEM0_API_KEY` | Mem0 API key | ✅ |
| `OPENAI_API_KEY` | For LLM-as-a-Judge evaluation | ✅ |
| `JUDGE_MODEL` | Model for evaluation (default: gpt-4o) | ❌ |

## 📁 Project Structure

```
memanto-benchmark/
├── README.md                 # This file
├── requirements.txt          # Python dependencies
├── .env.example              # Environment template
├── run_benchmark.py          # Main entry point
├── benchmarks/
│   ├── __init__.py
│   ├── base.py               # Abstract benchmark runner
│   ├── memanto_adapter.py    # Memanto framework adapter
│   ├── mem0_adapter.py       # Mem0 framework adapter
│   ├── scenario_a.py         # Context-Overhead & Latency Sprint
│   ├── scenario_b.py         # Shifting Persona & Temporal Tracking
│   └── evaluator.py          # LLM-as-a-Judge evaluator
├── datasets/
│   ├── technical_logs.json   # Scenario A dataset
│   └── persona_evolution.json # Scenario B dataset
├── reports/
│   └── (generated reports)
└── tests/
    ├── test_adapters.py
    └── test_evaluator.py
```

## 🔬 Experimental Design

### Isolation & Controls
- **Same LLM backend** for both frameworks (configurable)
- **Identical datasets** fed to both systems
- **Same host environment** — single machine, single Python process
- **Configurable batch sizes** and session counts
- **3 runs per scenario** with statistical aggregation

### Reproducibility
- All datasets are version-controlled in `datasets/`
- Exact dependency versions pinned in `requirements.txt`
- Random seeds set for deterministic evaluation
- Environment documented via `.env.example`

## 📊 Output

The benchmark generates:
1. **Console summary** — key metrics comparison table
2. **JSON report** — `reports/benchmark_results.json`
3. **HTML report** — `reports/benchmark_report.html` with charts

## 📄 License

MIT
