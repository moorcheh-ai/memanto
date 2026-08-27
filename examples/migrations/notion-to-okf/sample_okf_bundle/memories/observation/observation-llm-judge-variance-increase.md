---
type: observation
title: "Observation: LLM judge variance increases above temperature 0.1"
timestamp: "2025-11-10T13:45:00+00:00"
tags:
  - observation
  - evaluation
  - LLM
  - notion-db:research-notes
x_memanto:
  type: observation
  source: notion
  confidence: 0.7
  provenance: imported
---

Observed significant score variance in LLM-as-judge eval runs when temperature > 0.1. At temperature=0.0, GPT-4o-mini with seed=42 produces deterministic scores. Recommendation: always pin temperature=0.0 and document judge model and version in benchmark methodology.

---
[Supporting data]
- Source: notion:b8c9d0e1-f2a3-4567-1234-678901234567
- Notion database: Research Notes
- Notion URL: https://notion.so/b8c9d0e1f2a3
- Notion status: Active
- Priority: Low
- Last edited: 2025-11-10T14:00:00+00:00
- Source created_at: 2025-11-10T13:45:00+00:00
