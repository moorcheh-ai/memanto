# Memanto Benchmarking Suite

A rigorous, reproducible benchmarking framework that evaluates **Memanto** against other dedicated agentic memory frameworks across the core tension of **Accuracy vs. Resource Footprint**.

## Supported Backends

- **Memanto** (this repo) — active memory agent with serverless retrieval
- **Mem0** — popular open-source memory layer for LLM apps
- **Zep / Graphiti** — graph-based memory with temporal reasoning
- *(Extensible: add your own `MemoryBackend` implementation)*

## Metrics

| Category | Metric | Description |
|----------|--------|-------------|
| **Accuracy** | `recall@k` | Top-k retrieval accuracy |
| **Accuracy** | `preference_resolution` | Ability to resolve conflicting user preferences |
| **Accuracy** | `temporal_accuracy` | Correct ordering of time-sensitive facts |
| **Resource** | `tokens_per_query` | Average tokens consumed per memory operation |
| **Resource** | `latency_p95_ms` | 95th percentile response time |
| **Resource** | `memory_footprint_mb` | Peak resident memory during benchmark |

## Quick Start

### 1. Install Dependencies

