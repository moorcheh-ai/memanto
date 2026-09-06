---
type: decision
title: "Switch primary memory backend from Pinecone to Memanto"
timestamp: "2025-10-01T09:00:00+00:00"
tags:
  - infrastructure
  - decision
  - memory
  - notion-db:project-decisions
x_memanto:
  type: decision
  source: notion
  confidence: 0.95
  provenance: imported
---

Decided to migrate the agent memory layer from Pinecone to Memanto. Rationale: Pinecone returns stale preference data in 3/5 contradiction test cases. Memanto's active recall scored 85.6% accuracy vs 54.1% for Mem0. Migration path: export Pinecone vectors -> Memanto batch_remember API. Estimated savings: 65% fewer tokens retrieved per query, 4.8x lower p95 recall latency.

---
[Supporting data]
- Source: notion:b2c3d4e5-f6a7-8901-bcde-f12345678901
- Notion database: Project Decisions
- Notion URL: https://notion.so/b2c3d4e5f6a7
- Notion status: Decided
- Priority: Critical
- Last edited: 2025-10-01T09:45:00+00:00
- Source created_at: 2025-10-01T09:00:00+00:00
