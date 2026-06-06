# Memanto Benchmarking Suite

A rigorous, reproducible benchmarking framework that evaluates **Memanto** against other agentic memory frameworks across the core tension of **Accuracy vs. Resource Footprint**.

## Supported Backends

- **Memanto** (this repo) — active memory agent with serverless retrieval
- **Mem0** — popular open-source memory layer for LLM apps
- **Zep / Graphiti** — graph-based memory with entity extraction
- *(Extensible: add more backends via the `BaseMemoryBackend` interface)*

## Metrics

| Category | Metric | Description |
|----------|--------|-------------|
| **Accuracy** | Recall@K | Fraction of relevant memories retrieved in top-K |
| **Accuracy** | Preference Resolution | Correctly resolving conflicting user preferences over time |
| **Accuracy** | Temporal Consistency | Maintaining consistency across multi-session conversations |
| **Resource** | Tokens per Query | Total tokens consumed (prompt + retrieval + response) |
| **Resource** | p95 Latency | 95th percentile response time |
| **Resource** | Memory Growth Rate | Storage overhead per conversation turn |

## Quick Start

### 1. Install Dependencies

