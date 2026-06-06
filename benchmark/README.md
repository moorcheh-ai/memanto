# Memanto Benchmarking Suite

A rigorous, reproducible benchmarking framework that pits **Memanto** against other dedicated agentic memory frameworks to stress-test their production efficiency across the core tension: **Accuracy vs. Resource Footprint**.

## Supported Frameworks

- **Memanto** (this repo) - Active memory agent with serverless retrieval
- **Mem0** - Popular dedicated memory platform
- **Zep/Graphiti** - Graph-based memory with temporal reasoning
- **Letta** (formerly MemGPT) - LLM-based memory management

## Benchmark Dimensions

| Dimension | Metric | Description |
|-----------|--------|-------------|
| **Accuracy** | Recall@K, MRR, Preference Resolution | How well does the system retrieve relevant memories? |
| **Token Efficiency** | Tokens per query, Context bloat ratio | How many tokens are consumed for retrieval? |
| **Latency** | p50, p95, p99 retrieval latency | How fast are retrieval operations? |
| **Scalability** | Memory usage growth, Query throughput | How does it scale with memory size? |

## Quick Start

