# 🐜 The Great Agentic Memory Showdown: Memanto vs Mem0

**Bounty submission for [#639](https://github.com/moorcheh-ai/memanto/issues/639)**

## Scenario: Evolving AI Companion Preferences (Scenario B)

A user interacts with an AI companion across **two phases**, deliberately shifting 5 preferences:

| Preference | Phase 1 (Initial) | Phase 2 (Updated) |
|---|---|---|
| UI Theme | Dark mode | Light mode |
| Work hours | 10pm–2am | 9am–5pm |
| Language | Rust | Go |
| Frontend | Next.js | Remix |
| Answer style | Short & direct | Detailed explanations welcome |

Then Phase 3 queries the system with targeted recall questions to measure whether it surfaces the *updated* preference or the stale one.

## Results

```
| Metric             | Memanto   | Mem0    |
|--------------------|-----------|---------|
| Retrieval Accuracy | 80.0%     | 20.0%   |
| p50 Latency (ms)   | 2,181.7   | 318.5   |
| p95 Latency (ms)   | 3,235.7   | 396.6   |
| Remember calls     | 1         | 10      |
| Recall calls       | 5         | 5       |
```

## Key Findings

### Memanto (80% accuracy)
- ✅ Correctly surfaces the most recent preference with temporal awareness ("Mahfuz *started* as dark mode but *recently switched* to light mode")
- ✅ Work hours, answer style, frontend framework all updated correctly
- ❌ Programming language (Go/Rust): retrieves Phase 1 (Rust) rather than Phase 2 (Go) — likely a chunking/retrieval ordering issue when Phase 2 update is semantically close to Phase 1 content
- ⚠️ Higher latency (~2s p50) due to RAG pipeline — expected tradeoff for richer, generative answers

### Mem0 (20% accuracy)
- ✅ Fast retrieval (~320ms p50) — purpose-built for low-latency memory
- ❌ Returns stale/initial preferences on 4/5 queries — dark mode (Phase 1) returned even after light mode update (Phase 2)
- ❌ Search returns empty for 2 queries — suggests embedding/index lag or filter issue
- ⚠️ Mem0 excels at fast lookup of static facts, but struggles with preference *drift* — it tends to return the most frequently-mentioned version rather than the most recent

## Architecture Comparison

| | Memanto (Moorcheh) | Mem0 |
|---|---|---|
| Model | RAG over document namespace | Vector search + fact extraction |
| Update strategy | Append + RAG re-ranking | Overwrite/merge |
| Strength | Temporal context, evolving preferences | Speed, simple facts |
| Weakness | Latency, similar-text drift | Preference updates |

## Reproducibility

### Requirements
```
Python 3.10+
uv (https://astral.sh/uv)
```

### Setup
```bash
git clone https://github.com/moorcheh-ai/memanto
cd memanto
uv init && uv add memanto mem0ai tabulate

# Set your API keys
export MOORCHEH_API_KEY=your_key
export MEM0_API_KEY=your_key
```

### Run
```bash
uv run python benchmark.py
```

Results are saved to `results.json`.

## Environment
- Python 3.13.5
- `moorcheh-sdk==1.3.5` (via `memanto` package)
- `mem0ai==0.1.98`
- Run date: 2026-06-08
- Platform: Linux x64
