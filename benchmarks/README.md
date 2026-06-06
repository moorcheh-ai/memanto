# Memanto Benchmarking Suite

A rigorous, reproducible benchmarking framework that evaluates **Memanto** against other dedicated agentic memory frameworks across the core tension of **Accuracy vs. Resource Footprint**.

## Supported Frameworks

- **Memanto** (this repo)
- **Mem0** (https://github.com/mem0ai/mem0)
- **Zep/Graphiti** (https://github.com/getzep/graphiti)

## Benchmarks

### 1. Conversation Recall Benchmark
Tests an agent's ability to recall facts from multi-turn conversations of varying length.

### 2. Preference Resolution Benchmark
Tests an agent's ability to resolve conflicting preferences stated at different points in time.

### 3. Token Efficiency Benchmark
Measures tokens consumed per accurate recall.

### 4. Latency Benchmark
Measures p50, p95, p99 latency for memory operations.

## Quick Start

