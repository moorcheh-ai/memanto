# Memanto vs Mem0 Benchmark Suite: Shifting Persona Test

This directory contains a reproducible benchmarking suite that pits **Memanto** against **Mem0** (an established agentic memory framework). 

It specifically evaluates **Scenario B: The Shifting Persona & Temporal Tracking Test**. As agents interact over multiple sessions, user preferences can change drastically. This benchmark tests how effectively both frameworks isolate current preferences without bloating the active context window or increasing latency.

## Prerequisites

1. Python 3.9+
2. A free **Moorcheh API Key** (Get one at [moorcheh.ai](https://moorcheh.ai))
3. A **Groq API Key** (Used for Mem0's internal LLM calls and the LLM-as-a-judge)
4. An **OpenAI API Key** (Optional fallback if not using Groq)

## Setup Instructions

1. Clone this repository and navigate to this folder:
   ```bash
   cd examples/benchmarks/memanto_vs_mem0_persona_shift
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Or `venv\Scripts\activate` on Windows
   pip install -r requirements.txt
   ```

3. Configure your API keys:
   ```bash
   cp .env.example .env
   ```
   Open the `.env` file and insert your `MOORCHEH_API_KEY`, `GROQ_API_KEY`, and optional `OPENAI_API_KEY`.

## Running the Benchmark

Simply run the benchmark script:

```bash
python benchmark.py
```

## Methodology

### Dataset (`dataset.py`)
A simulated 4-session user interaction where the user starts by hating romance and loving action, watches a romance and likes it, and finally burns out on action entirely. The final expected state requires the memory system to synthesize this timeline properly.

### Adapters (`memory_layers.py`)
Wrappers around Memanto and Mem0 to ensure they are fed identical data and evaluated fairly.

### LLM Judge (`judge.py`)
Uses `llama-3.3-70b-versatile` via Groq to grade the retrieved context (0-100) based on how well it isolated the user's current preferences from their outdated ones.

### Output
The script prints a clean table directly to the terminal using `rich`, displaying:
- **Total Tokens Ingested**
- **Tokens Retrieved**
- **p95 Latency (s)**
- **Accuracy Score (0-100)**
