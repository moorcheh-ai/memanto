# Memanto Benchmarking Suite

A rigorous, reproducible benchmarking suite that pits **Memanto** against other dedicated agentic memory frameworks to stress-test their production efficiency across **Accuracy vs. Resource Footprint**.

## Supported Frameworks

- **Memanto** (this repo)
- **Mem0** (https://github.com/mem0ai/mem0)
- **Zep/Graphiti** (https://github.com/getzep/graphiti)
- **Hindsight** (https://github.com/hindsightlabs/hindsight)
- **Letta** (https://github.com/letta-ai/letta)

## Metrics

| Metric | Description |
|--------|-------------|
| Recall Accuracy | % of correctly retrieved facts from memory |
| Latency (p50/p95/p99) | Time to store/retrieve memories |
| Token Efficiency | Tokens used per memory operation |
| Context Window Utilization | % of context window consumed |
| Background Processing Overhead | CPU/memory usage during background ops |

## Quick Start

