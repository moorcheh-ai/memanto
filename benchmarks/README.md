# Memanto Benchmarking Suite

A rigorous, reproducible benchmarking framework that evaluates Memanto against other agentic memory frameworks across the core dimensions of **Accuracy vs. Resource Footprint**.

## Supported Frameworks

- **Memanto** (this repo)
- **Mem0**
- **Zep/Graphiti**
- **Hindsight**
- **Letta**

## Benchmarks

### 1. Recall Accuracy Benchmark
Tests how well each framework retrieves relevant memories given a query, measured by:
- **Precision@K**: Fraction of retrieved memories that are relevant
- **Recall@K**: Fraction of relevant memories that are retrieved
- **MRR (Mean Reciprocal Rank)**: Position of first relevant result

### 2. Token Efficiency Benchmark
Measures the token overhead of each framework:
- **Storage tokens**: Tokens used to store memories
- **Retrieval tokens**: Tokens used during retrieval queries
- **Context window bloat**: Ratio of metadata to actual content

### 3. Latency Benchmark
Measures response times under load:
- **p50/p95/p99 latency**: Percentile response times
- **Throughput**: Queries per second
- **Cold start latency**: Time to first response

### 4. Preference Resolution Benchmark
Tests nuanced, multi-hop preference recall:
- **Single-hop**: Direct preference queries
- **Multi-hop**: Inferential queries requiring combining multiple memories
- **Temporal**: Time-sensitive preference evolution

## Quick Start

