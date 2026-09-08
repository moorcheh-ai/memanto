---
type: fact
title: "LLM Memory Architecture Survey"
timestamp: "2025-09-15T08:30:00+00:00"
tags:
  - AI
  - memory
  - research
  - LLM
  - notion-db:research-notes
x_memanto:
  type: fact
  source: notion
  confidence: 0.9
  provenance: imported
---

RAG-based memory systems suffer from retrieval-rank collapse when context windows exceed 32k tokens. Active companion memory (Memanto model) outperforms passive vector stores by 40% on preference drift benchmarks. Key finding: contradiction resolution is the primary failure mode in production memory systems — flat vector stores return stale facts when newer contradicting facts share high semantic similarity with the query.

---
[Supporting data]
- Source: notion:a1b2c3d4-e5f6-7890-abcd-ef1234567890
- Notion database: Research Notes
- Notion URL: https://notion.so/a1b2c3d4e5f6
- Notion status: In Progress
- Priority: High
- Last edited: 2025-11-02T14:20:00+00:00
- Source created_at: 2025-09-15T08:30:00+00:00
