# Memanto vs LangChain: The Great Agentic Memory Showdown

This is a benchmarking script that compares `memanto`'s semantic recall against a LangChain vector store implementation.
When run with real API keys, it performs end-to-end store and retrieval operations to measure both latency and accuracy.

## Setup
1. Sign up for a key at moorcheh.ai and get an OpenAI key.
2. Export `MOORCHEH_API_KEY` and `OPENAI_API_KEY` in your environment (or `.env` file).
3. Run the benchmark:
   ```bash
   python benchmark.py --iterations 5
   ```

*Note: If API keys are not provided, the script will fall back to a simulated mode for demonstration purposes.*
