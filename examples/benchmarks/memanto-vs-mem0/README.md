# Memanto vs. Mem0 - Benchmark Challenge

This directory contains a reproducible benchmarking suite that pits **Memanto** against **Mem0**, focusing on **Scenario B: The Shifting Persona & Temporal Tracking Test**.

## Scenario Description

The benchmark evaluates how efficiently both memory frameworks handle dynamic and contradicting user preferences over time. It simulates a user changing their diet multiple times and tracks:
1. **Write Latency**: Time taken to ingest new information.
2. **Read Latency**: Time taken to retrieve the most up-to-date and accurate preference without retrieving the outdated ones.

## Prerequisites

Ensure you have the required API keys exported in your environment:

```bash
export MOORCHEH_API_KEY="your-moorcheh-api-key"
export OPENAI_API_KEY="your-openai-api-key"
```

## Installation

Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Running the Benchmark

Execute the benchmarking script:

```bash
python benchmark.py
```

## Expected Results & Conclusion

Memanto typically avoids context window bloat by actively tagging and resolving outdated statements, whereas passive graph/vector dumping systems (like Mem0) might retrieve all contradicting statements or take longer to parse them out. Memanto also aims for lower latency by offloading processing to the active companion agent.

**Social Media Showcase:**
Check out the discussion and in-depth metrics on [Reddit / r/AgenticMemory](https://www.reddit.com/r/AgenticMemory) or X [@moorcheh_ai].
