# Memanto Benchmarking Suite

This directory contains a rigorous, reproducible benchmarking suite that pits **Memanto** against other dedicated agentic memory frameworks to stress-test their production efficiency.

## Overview

The benchmark evaluates the core tension of agent infrastructure: **Accuracy vs. Resource Footprint**.

### Supported Competitors

- **Memanto** (this repo)
- **Mem0**
- **Zep/Graphiti**
- **Hindsight**
- **Letta**

## Metrics

| Metric | Description |
|--------|-------------|
| Token Efficiency | Tokens consumed per memory operation |
| p95 Latency | 95th percentile response time |
| Preference Resolution | Accuracy of nuanced preference recall |
| Context Window Bloat | Growth rate of context window |
| Background Processing Latency | Time for background memory processing |

## Quick Start

