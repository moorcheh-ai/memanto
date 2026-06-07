# Benchmark Results — Fabric Entertainment Curator

**Scenario**: entertainment-curator-temporal-drift
**Sessions**: 20
**LLM Judge**: keyword-overlap (OPENAI_API_KEY not set)
**Host**: Python 3.10+, tiktoken 0.9.0, single-process sequential execution

## Results

| Backend | Avg Retrieved Tokens | p95 Latency (ms) | Accuracy | Stale Rate |
|---------|---------------------|------------------|----------|------------|
| `memanto_active_digest` | 312.4 | 0.531 | 78.3% | 5.0% |
| `mem0_local` | 1487.2 | 0.419 | 74.0% | 62.0% |
| `append_only_baseline` | 1487.2 | 0.281 | 74.0% | 62.0% |

## Key Findings

The **memanto active-digest** backend demonstrates substantially lower token
overhead and stale contamination compared to both baselines. By detecting and
superseding contradicted preferences at write time, only current facts are
injected into the agent context — the core architectural advantage described in
[arXiv:2604.22085](https://arxiv.org/abs/2604.22085).

### Token Efficiency

Active-digest stores only non-superseded memories. After 20 sessions of
evolving preferences, ~15 current entries survive from 60 total writes.
Passive backends accumulate all 60, creating 4-5x token overhead per recall.

### Stale Contamination

Passive backends retain contradicted facts (e.g. "Alex loves sci-fi" from
session 1 survives even after session 11 explicitly overrides it).
Active-digest supersedes conflicting entries at write time, achieving near-zero
stale contamination.

## Reproduction

```bash
pip install -r requirements.txt
python run_benchmark.py --output results/sample_results.json \
                         --markdown results/sample_results.md
python -m unittest discover -s . -p test_*.py
```

To enable LLM judge (recommended for full accuracy scoring):

```bash
export OPENAI_API_KEY=sk-...
export MOORCHEH_API_KEY=<key from moorcheh.ai>
python run_benchmark.py
```
