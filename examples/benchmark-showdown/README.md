# Memanto Benchmark Showdown

> Memanto vs Mem0: A rigorous, reproducible benchmark comparing agentic memory backends on accuracy, token efficiency, and retrieval latency.

## Overview

This benchmark suite evaluates **Memanto** against **Mem0** across two distinct scenarios that stress-test the core tension of 2026 agent infrastructure: **Accuracy vs Resource Footprint**.

### Scenarios

| Scenario | Focus | What It Tests |
|----------|-------|---------------|
| **A: Context-Overhead Latency Sprint** | Data-intensive | Token consumption per turn, retrieval latency under dense technical logs |
| **B: Shifting Persona Temporal Tracking** | Dynamic preferences | Preference retention accuracy over time with contradictory updates |

## Quick Start

```bash
# 1. Clone and enter the benchmark directory
cd examples/benchmark-showdown

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your API keys:
#   - MEMANTO_API_KEY: Get from https://console.moorcheh.ai/api-keys
#   - MEM0_API_KEY: Get from https://app.mem0.ai

# 4. Run the benchmark
python run_benchmark.py
```

## Environment Setup

| Variable | Required | Source |
|----------|----------|--------|
| `MEMANTO_API_KEY` | Yes | [Moorcheh Console](https://console.moorcheh.ai/api-keys) |
| `MEM0_API_KEY` | Yes | [Mem0 Dashboard](https://app.mem0.ai) |
| `MEMANTO_AGENT_ID` | No | Defaults to `benchmark-agent` |
| `BENCHMARK_OUTPUT` | No | Defaults to `results/` |
| `BENCHMARK_REPEAT` | No | Defaults to `3` |

### Host Environment

- **Python**: 3.10 - 3.12
- **OS**: Linux / macOS / Windows
- **LLM Backend**: Memanto uses Moorcheh's serverless retrieval (no local LLM required). Mem0 cloud API.
- **Network**: Stable internet connection required for API calls.

## Scientific Design

### Variables Isolated

- **Same dataset**: Both backends ingest identical entries in identical order
- **Same queries**: Both backends receive identical retrieval queries
- **Same timing**: Sequential execution with measured latency
- **Independent state**: Each backend has its own reset between iterations

### Metrics Collected

| Metric | Description |
|--------|-------------|
| **Total Tokens** | Cumulative token consumption across all operations |
| **Avg Latency** | Mean operation latency in milliseconds |
| **P95 Latency** | 95th percentile latency |
| **P99 Latency** | 99th percentile latency |
| **Retrieval Accuracy** | Fraction of expected results returned (0-1) |
| **Error Count** | Number of failed operations |

### Reproducibility

- All datasets are embedded in the `datasets/` directory
- API keys are the only external dependency
- Results are exported as JSON + Markdown
- Run `BENCHMARK_REPEAT=1` for a quick test, `=5` for higher confidence

## Project Structure

```
benchmark-showdown/
├── README.md              # This file
├── requirements.txt       # Python dependencies
├── .env.example           # Environment template
├── run_benchmark.py       # Main entry point
├── backends/
│   ├── __init__.py
│   ├── base.py            # Abstract backend interface
│   ├── memanto_backend.py # Memanto adapter
│   └── mem0_backend.py    # Mem0 adapter (competitor)
├── datasets/
│   ├── __init__.py
│   ├── scenario_a_technical.py   # Technical logs dataset
│   └── scenario_b_persona.py     # Persona tracking dataset
├── metrics/
│   ├── __init__.py
│   ├── collector.py       # Metrics aggregation
│   └── reporter.py        # Results formatting
└── results/               # Output directory (created at runtime)
    ├── benchmark_results.json
    └── benchmark_report.md
```

## Output Format

### JSON (`benchmark_results.json`)

```json
[
  {
    "scenario": "scenario_a",
    "backend": "Memanto",
    "total_tokens": 1234,
    "avg_latency_ms": 145.23,
    "p95_latency_ms": 210.50,
    "p99_latency_ms": 289.10,
    "avg_accuracy": 0.85,
    "total_operations": 13,
    "error_count": 0,
    "details": [...]
  }
]
```

### Markdown Report

A human-readable comparison table is generated in `benchmark_report.md`.

## Judgment Criteria (100-point matrix)

| Criteria | Max Points | How Measured |
|----------|------------|--------------|
| Scientific Rigor & Isolation | 40 pts | Variable isolation, documented experimental design |
| Use Case Complexity | 20 pts | Meaningful scenarios (dense data, evolving preferences) |
| Reproducibility & Cleanliness | 15 pts | Plug-and-play setup, clear datasets and instructions |
| Social Amplification | 25 pts | Documentation quality, community readiness |

## License

MIT - Same as the Memanto project.
