# Memanto Benchmarking Suite

A rigorous, reproducible benchmarking suite that pits **Memanto** against other dedicated agentic memory frameworks to stress-test their production efficiency across **Accuracy vs. Resource Footprint**.

## Supported Frameworks

- **Memanto** (this repo) - Active memory agent with serverless retrieval
- **Mem0** - Popular dedicated memory platform
- **Zep/Graphiti** - Graph-based memory with temporal reasoning
- **Letta** - Agent framework with built-in memory

## Benchmark Dimensions

| Metric | Description | Why It Matters |
|--------|-------------|--------------|
| **Recall Accuracy** | Correct retrieval of relevant memories | Core functionality |
| **Token Efficiency** | Tokens consumed per memory operation | Cost at scale |
| **Latency (p50/p95/p99)** | Response time percentiles | User experience |
| **Context Window Bloat** | Growth of context with conversation history | Long-term scalability |
| **Preference Resolution** | Accuracy of nuanced, multi-hop preference recall | Agent personalization |

## Quick Start

