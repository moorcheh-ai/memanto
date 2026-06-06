# Memanto vs Letta Benchmark

Bounty submission for: https://github.com/moorcheh-ai/memanto/issues/639

## Setup

```bash
pip install -r requirements.txt
export MEMANTO_API_KEY=your_key_here
python memanto_benchmark.py
```

## Scenarios

1. **Technical Logs**: 100 dense system log entries, tests token efficiency and p95 latency
2. **Evolving Preferences**: 20 sessions with shifting user preferences, tests accuracy

## Metrics

- Total tokens consumed/retrieved
- P95 retrieval latency (ms)
- Retrieval accuracy (LLM-as-judge)

## Results

Results are printed as JSON for easy comparison and visualization.
