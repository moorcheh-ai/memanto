# Memanto Benchmarking Suite

A rigorous, reproducible benchmarking suite that pits **Memanto** against other dedicated agentic memory frameworks to stress-test their production efficiency across the core tension of **Accuracy vs. Resource Footprint**.

## Supported Frameworks

- **Memanto** (this repo)
- **Mem0** (https://github.com/mem0ai/mem0)
- **Zep/Graphiti** (https://github.com/getzep/graphiti)
- **Letta** (https://github.com/letta-ai/letta)

## Benchmark Dimensions

| Dimension | Description | Metrics |
|-----------|-------------|---------|
| **Recall Accuracy** | Ability to retrieve relevant memories given a query | Precision@K, Recall@K, MRR, NDCG |
| **Preference Resolution** | Ability to resolve nuanced, conflicting user preferences | Preference Accuracy, Conflict Resolution Rate |
| **Token Efficiency** | Tokens consumed per memory operation | Tokens per query, compression ratio |
| **Latency** | Time to complete memory operations | p50, p95, p99 latency |
| **Scalability** | Performance under increasing memory load | Query time vs. memory count |

## Quick Start

### 1. Install Dependencies

