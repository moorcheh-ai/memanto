# Memanto vs Mem0 — Agent Memory Benchmark

> **BountyHub Benchmark Submission**  
> Comparing Moorcheh's information-theoretic retrieval (Memanto) against Mem0's vector-based agent memory.

## Overview

This benchmark evaluates two leading agent memory systems on the same document corpus and query set:

| System | Architecture | Ingestion Strategy | Retrieval |
|--------|-------------|-------------------|-----------|
| **Memanto** (Moorcheh) | Information-theoretic semantic search | Zero-extraction, instant indexing | Exact deterministic scoring |
| **Mem0** | ANN vector search (Qdrant) + LLM extraction | LLM-based fact extraction (or raw with `infer=False`) | Approximate nearest neighbor |

## What is Being Measured

1. **Relevance** (0–100): How closely retrieved passages match the query topic.
2. **Completeness** (0–100): Whether the retrieved context is sufficient to answer the query.
3. **Latency**: End-to-end retrieval time in milliseconds.

The judge is an LLM (OpenAI GPT-4o) prompted with a structured rubric to ensure consistency and eliminate human bias.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure API keys
cp .env.example .env
# Edit .env and add your keys

# 3. Run the benchmark
python benchmark.py
```

### Prerequisites

- **MOORCHEH_API_KEY** — Get one at [moorcheh.ai](https://moorcheh.ai)
- **OPENAI_API_KEY** — Used by Mem0 for embeddings and by the judge for scoring

## Benchmark Corpus

- **Document**: `sample_document.md` — A ~5,000-word technical history of AI agent memory systems from the 1950s to 2026.
- **Chunking**: 700-character chunks with 120-character overlap (RecursiveCharacterTextSplitter)
- **Queries**: 8 diverse questions spanning factual recall, temporal reasoning, comparative analysis, and benchmark scores.

## Project Structure

```
memanto-vs-mem0/
├── benchmark.py          # Main benchmark orchestrator
├── sample_document.md    # Document to ingest and query
├── queries.csv           # Test queries
├── judge_prompt.txt      # LLM-as-a-Judge evaluation rubric
├── requirements.txt      # Python dependencies
├── .env.example          # Required environment variables
└── results/              # Generated after run
    ├── results.csv       # Per-query raw scores
    ├── summary.json      # Aggregate metrics
    └── summary.md        # Human-readable report
```

## How It Works

1. **Ingestion**
   - The document is split into identical chunks for both systems.
   - **Memanto**: Chunks are uploaded to a Moorcheh namespace via `moorcheh-sdk`.
   - **Mem0**: Chunks are stored as agent memories using `mem0.Memory.add(..., infer=False)`.

2. **Retrieval**
   - Each query is issued to both systems with `top_k=5`.
   - Retrieved passages, along with their internal scores, are captured.

3. **Evaluation**
   - GPT-4o scores each result set on relevance and completeness using a standardized prompt.
   - Scores are averaged per system and compared.

4. **Reporting**
   - `results.csv` contains every query/system combination with raw scores.
   - `summary.json` and `summary.md` provide aggregate statistics and declare a winner.

## Expected Results

Based on the architectural advantages of information-theoretic retrieval (exact scoring, zero ingestion latency, no ANN approximation error), Memanto is expected to outperform Mem0 on both relevance and completeness, particularly for precise factual and temporal queries.

## Extending the Benchmark

- Swap `sample_document.md` with your own corpus.
- Edit `queries.csv` to test different query distributions.
- Change `JUDGE_MODEL` in `benchmark.py` to use Gemini or another model.
- Adjust `CHUNK_SIZE`, `CHUNK_OVERLAP`, or `TOP_K` to explore sensitivity.

## License

MIT — aligned with the Memanto project license.
