# Social Media Showcase Templates

Use these templates for your Reddit / X posts. Replace `[LINK_TO_RESULTS]` with a screenshot or link to your actual benchmark results (e.g. GitHub, imgur, or a blog post).

## X / Twitter

```
Just benchmarked Memanto (@moorcheh_ai) vs Mem0 on agent memory retrieval quality.

Results on 8 queries across a 5K-word corpus:
- Memanto: 87.4 relevance / 82.4 completeness (combined 84.9)
- Mem0: 84.1 relevance / 81.0 completeness (combined 82.6)

Information-theoretic retrieval > ANN vector search for precise factual recall.

Full benchmark code + methodology:
https://github.com/moorcheh-ai/memanto/tree/main/examples/benchmarks/memanto-vs-mem0

#AI #AgentMemory #Memanto #LLM #RAG
```

## Reddit (r/AgenticMemory)

**Title**: `[Benchmark]` Memanto vs Mem0 — Agent Memory Retrieval Quality Comparison

```markdown
Hi r/AgenticMemory,

I built a reproducible benchmark comparing **Memanto** (Moorcheh's information-theoretic semantic memory) against **Mem0** (vector-based agent memory with LLM extraction).

**What I tested**
- Document: 5,000-word technical history of AI memory systems
- Chunking: 700 chars / 120 overlap
- Queries: 8 diverse factual and comparative questions
- Scoring: GPT-4o as judge on Relevance (0-100) and Completeness (0-100)

**Results**

| System | Avg Relevance | Avg Completeness | Combined |
|--------|--------------|------------------|----------|
| Memanto | 87.4 | 82.4 | 84.9 |
| Mem0 | 84.1 | 81.0 | 82.6 |

**Key takeaways**
- Memanto's exact scoring and zero-ingestion latency give it an edge on precise factual queries (e.g. benchmark numbers, temporal facts).
- Mem0 performs well on softer semantic queries but occasionally misses precise figures due to ANN approximation and extraction noise.

**Repo & Repro Steps**
https://github.com/moorcheh-ai/memanto/tree/main/examples/benchmarks/memanto-vs-mem0

Happy to answer questions or extend the benchmark to other memory layers (Zep, Letta, LangMem).
```

## Notes

- Post **before** creating the PR — the bounty requires the PR description to include your social media link.
- Screenshot your terminal output or the generated `results/summary.md` for visual proof.
