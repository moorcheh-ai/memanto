# Memanto Benchmarking Suite

A rigorous, reproducible benchmarking framework that evaluates **Memanto** against other agentic memory frameworks (Mem0, Zep/Graphiti, Hindsight, Letta) across the core tension of **Accuracy vs. Resource Footprint**.

## Overview

This benchmark suite stress-tests memory frameworks on production-relevant metrics:

- **Accuracy**: Recall precision, preference resolution, context relevance
- **Token Efficiency**: Tokens consumed per memory operation
- **Latency**: p50/p95/p99 response times
- **Scalability**: Performance degradation under memory growth

## Supported Frameworks

| Framework | Identifier | Status |
|-----------|-----------|--------|
| Memanto | `memanto` | ✅ Fully supported |
| Mem0 | `mem0` | ✅ Supported |
| Zep/Graphiti | `zep` | ⚠️ Requires API key |
| Hindsight | `hindsight` | ⚠️ Requires local setup |
| Letta | `letta` | ⚠️ Requires local setup |

## Quick Start

### 1. Install Dependencies

