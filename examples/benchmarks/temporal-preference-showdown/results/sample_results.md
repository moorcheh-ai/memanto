# Temporal Preference Showdown — Results

**Scenario:** Shifting Persona — 5 sessions, evolving user preferences
**Queries:** 6 golden questions testing recall of CURRENT (not stale) facts

## Summary Table

| Metric | Memanto (active digest) | Mem0 (cloud) |
|--------|--------|--------|
| Accuracy | **100.0%** | 33.3% |
| Stale Rate | **0.0%** | **0.0%** |
| Tokens Ingested | 429 | **392** |
| Tokens Retrieved | **164** | 342 |
| Ingest p95 | 1,126.0 ms | **614.2 ms** |
| Retrieve p95 | **0.0 ms** | 879.9 ms |

## Per-Query Breakdown

### Memanto (active digest)

| Query | Result | Retrieved Context |
|-------|--------|-------------------|
| q1: What programming language does Alex pref... | ✅ Correct | programming language: Python is the standardized language across the company; co... |
| q2: Where does Alex live?... | ✅ Correct | city: Recently moved to Berlin from London.; job title: Engineering Lead; progra... |
| q3: What is Alex's current role and team siz... | ✅ Correct | team size: Team of 8 people; job title: Engineering Lead; programming language: ... |
| q4: What is Alex's diet?... | ✅ Correct | programming language: Python is the standardized language across the company; di... |
| q5: Does Alex prefer dark mode or light mode... | ✅ Correct | editor theme: Uses light mode; job title: Engineering Lead; city: Recently moved... |
| q6: How does Alex prefer to communicate asyn... | ✅ Correct | city: Recently moved to Berlin from London.; communication preference: Prefers v... |

### Mem0 (cloud)

| Query | Result | Retrieved Context |
|-------|--------|-------------------|
| q1: What programming language does Alex pref... | ✅ Correct | User migrated their entire backend to the Go programming language after three mo... |
| q2: Where does Alex live?... | ✅ Correct | User relocated from London to Berlin in May 2026, noting that London was too exp... |
| q3: What is Alex's current role and team siz... | ❌ Miss | User relocated from London to Berlin in May 2026, noting that London was too exp... |
| q4: What is Alex's diet?... | ❌ Miss | User relocated from London to Berlin in May 2026, noting that London was too exp... |
| q5: Does Alex prefer dark mode or light mode... | ❌ Miss | User now prefers Go over Python for backend development, citing its performance ... |
| q6: How does Alex prefer to communicate asyn... | ❌ Miss | User now prefers Go over Python for backend development, citing its performance ... |

## Methodology

- **Memanto backend**: Extracts typed facts via Claude Haiku; stores only
  the active digest. Newer facts replace older ones (conflict resolution).
- **Mem0 backend**: Real Mem0 cloud API. Stores conversation turns and
  retrieves via Mem0's own compression and semantic search.
- **Accuracy**: keyword matching against a golden dataset of current facts.
- **Tokens**: approximate (word count × 1.3), consistent across both backends.
- **Environment**: macOS, same ANTHROPIC_API_KEY for Memanto extraction,
  MEM0_API_KEY for Mem0 cloud.

_Benchmark built as part of [Memanto Issue #639](https://github.com/moorcheh-ai/memanto/issues/639)_