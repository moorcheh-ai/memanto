# Memanto Benchmarking Suite

A rigorous, reproducible benchmarking suite that pits **Memanto** against other dedicated agentic memory frameworks to stress-test their production efficiency across **Accuracy vs. Resource Footprint**.

## Supported Frameworks

- **Memanto** (this repo)
- **Mem0** - https://github.com/mem0ai/mem0
- **Zep/Graphiti** - https://github.com/getzep/graphiti
- **Letta** - https://github.com/letta-ai/letta

## Benchmarks

### 1. Memory Accuracy Benchmark
Tests how well each framework recalls facts, preferences, and relationships after varying numbers of interactions.

### 2. Token Efficiency Benchmark
Measures total tokens consumed for memory operations (storage, retrieval, context injection).

### 3. Latency Benchmark
Measures p50, p95, and p99 latency for memory operations under load.

### 4. Context Window Efficiency
Tests how well each framework manages growing context without losing critical information.

## Quick Start

