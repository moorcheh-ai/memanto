# Memanto vs Mem0 Benchmark Report

This benchmark evaluates retrieval quality and latency of **Memanto** (Moorcheh) against **Mem0** on a shared document corpus.

## Methodology

- **Document**: `sample_document.md`
- **Chunks**: 18 (700 chars, 120 overlap)
- **Queries**: 8
- **Top-K retrieved**: 5
- **Judge model**: gpt-4o
- **Dimensions**: Relevance (0-100) and Completeness (0-100)

## Aggregate Results

| System | Queries | Avg Relevance | Avg Completeness | Combined | Avg Latency (ms) |
|--------|---------|---------------|------------------|----------|------------------|
| memanto |       8 |         62.88 |            62.88 |    62.88 |          1905.57 |
| mem0   |       8 |         54.75 |            54.75 |    54.75 |             0.02 |

**Winner**: Memanto with combined score 62.88

## Per-Query Breakdown

### What were the main limitations of early expert systems like MYCIN and DENDRAL?

- **Memanto**: Rel=75, Comp=75, Lat=2644.43ms
- **Mem0**: Rel=75, Comp=75, Lat=0.03ms

### How did recurrent neural networks contribute to machine memory before transformers?

- **Memanto**: Rel=68, Comp=68, Lat=1634.81ms
- **Mem0**: Rel=70, Comp=70, Lat=0.02ms

### What is the "lost in the middle" problem in long context windows?

- **Memanto**: Rel=61, Comp=61, Lat=1403.68ms
- **Mem0**: Rel=61, Comp=61, Lat=0.02ms

### How does Mem0 extract and store user preferences from conversations?

- **Memanto**: Rel=58, Comp=58, Lat=2096.17ms
- **Mem0**: Rel=45, Comp=45, Lat=0.02ms

### What are the key differences between Zep's graph approach and Memanto's typed semantic memory?

- **Memanto**: Rel=65, Comp=65, Lat=1951.63ms
- **Mem0**: Rel=49, Comp=49, Lat=0.02ms

### What benchmark scores did Memanto achieve on LongMemEval and LoCoMo in 2026?

- **Memanto**: Rel=60, Comp=60, Lat=1730.34ms
- **Mem0**: Rel=49, Comp=49, Lat=0.01ms

### How does information-theoretic retrieval differ from traditional ANN vector search?

- **Memanto**: Rel=48, Comp=48, Lat=2134.57ms
- **Mem0**: Rel=29, Comp=29, Lat=0.02ms

### What are the three primitives provided by Memanto?

- **Memanto**: Rel=68, Comp=68, Lat=1648.95ms
- **Mem0**: Rel=60, Comp=60, Lat=0.02ms

