# Memanto Benchmarking Suite

A rigorous, reproducible benchmarking framework that evaluates **Memanto** against other dedicated agentic memory frameworks across the core tension of **Accuracy vs. Resource Footprint**.

## Supported Frameworks

- **Memanto** (this repo)
- **Mem0** - https://github.com/mem0ai/mem0
- **Zep/Graphiti** - https://github.com/getzep/graphiti
- **Letta** - https://github.com/letta-ai/letta

## Benchmarks

### 1. Token Efficiency Benchmark (`token_efficiency/`)

Measures how many tokens each framework consumes to achieve a target recall accuracy. Lower is better.

**Metrics:**
- Total tokens consumed per interaction
- Tokens per correctly recalled fact
- Context window utilization ratio

### 2. Latency Benchmark (`latency/`)

Measures p50, p4.95, and p99 latency for memory operations under varying load.

**Metrics:**
- `store()` latency
- `retrieve()` latency  
- End-to-end round-trip latency
- Cold-start vs. warm-start performance

### 3. Preference Resolution Benchmark (`preference_resolution/`)

Tests nuanced, multi-hop preference recall across long conversation histories.

**Metrics:**
- Preference accuracy (exact match, semantic similarity)
- Preference drift over time
- Conflicting preference resolution

### 4. Resource Footprint Benchmark (`resource_footprint/`)

Measures CPU, memory, and disk usage during sustained operation.

**Metrics:**
- Peak memory usage
- Average CPU utilization
- Disk I/O and storage growth
- Background processing overhead

## Quick Start

