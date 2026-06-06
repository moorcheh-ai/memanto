# Memanto Benchmarking Suite

A rigorous, reproducible benchmarking framework that evaluates **Memanto** against other agentic memory frameworks across the core tension of **Accuracy vs. Resource Footprint**.

## Supported Frameworks

- **Memanto** (this repo) - Active memory agent with serverless retrieval
- **Mem0** - Dedicated memory platform for AI agents
- **Zep/Graphiti** - Graph-based memory with temporal reasoning
- **Letta** - Memory-first agent framework

## Benchmarks

### 1. Conversation Memory Benchmark (`conversation/`)
Tests multi-turn conversation memory with:
- **Accuracy**: Correct recall of facts, preferences, and context
- **Token Efficiency**: Tokens used per retrieval
- **Latency**: p50, p95, p99 response times
- **Scalability**: Performance as conversation history grows

### 2. Agent Workflow Benchmark (`agent_workflow/`)
Tests long-running agent workflows with:
- **Goal Completion Rate**: Successful task completion
- **Context Window Efficiency**: No unnecessary context bloat
- **Memory Update Accuracy**: Correct incorporation of new information

### 3. Synthetic Data Generator (`data_generator/`)
Generates realistic conversation and workflow data for consistent evaluation.

## Quick Start

