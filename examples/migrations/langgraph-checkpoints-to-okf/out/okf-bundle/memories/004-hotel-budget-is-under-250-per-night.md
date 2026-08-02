---
type: preference
title: Hotel budget is under $250 per night.
description: Agent memory migrated from a LangGraph SqliteSaver checkpoint (thread
  'alex-travel', turn 2).
resource: langgraph-checkpoint://alex-travel
tags:
- langgraph
- checkpoint-migration
- alex-travel
- preference
timestamp: '2026-08-02T23:34:15.745102+00:00'
x_memanto:
  type: preference
  confidence: 0.85
  source: langgraph-checkpoints
thread_id: alex-travel
turn: 2
checkpoint_id: 1f18ecaa-cb91-600e-800d-e36cc4d14466
checkpoint_step: 13
extraction_rule: under \$(\d+) a night
---

Hotel budget is under $250 per night.

## Provenance

- Source: LangGraph `SqliteSaver` checkpoint store (`checkpoints.sqlite`)
- Thread: `alex-travel` · Turn: 2 · Checkpoint: `1f18ecaa-cb91-600e-800d-e36cc4d14466` (step 13)
- Extraction rule: `under \$(\d+) a night`
- Migrated: 2026-08-02T23:34:15.969130+00:00

Migrated with the LangGraph → OKF adapter. See the
[LangGraph persistence docs](https://langchain-ai.github.io/langgraph/concepts/persistence/).
