# Memanto Benchmarking Suite

A rigorous, reproducible benchmarking suite that pits **Memanto** against other dedicated agentic memory frameworks to stress-test their production efficiency across the core tension: **Accuracy vs. Resource Footprint**.

## Supported Frameworks

- **Memanto** (this repo) - Active companion agent with serverless retrieval
- **Mem0** - Dedicated memory platform
- **Zep/Graphiti** - Graph-based memory (coming soon)
- **Letta** - Agent framework with memory (coming soon)

## Metrics

| Metric | Description |
|--------|-------------|
| Accuracy | Correct recall of stored facts/preferences |
| Precision@K | Relevance of retrieved memories |
| Latency (p50/p95/p99) | Response time percentiles |
| Token Usage | Total tokens consumed (input + output) |
| Memory Footprint | Peak RAM usage during operations |
| Throughput | Operations per second |

## Quick Start

### 1. Install Dependencies

