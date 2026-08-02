---
type: fact
title: User United MileagePlus number is 8842-1190.
description: Agent memory migrated from a LangGraph SqliteSaver checkpoint (thread
  'alex-travel', turn 5).
resource: langgraph-checkpoint://alex-travel
tags:
- langgraph
- checkpoint-migration
- alex-travel
- fact
timestamp: '2026-08-02T23:49:43.599832+00:00'
x_memanto:
  type: fact
  confidence: 0.85
  source: langgraph-checkpoints
thread_id: alex-travel
turn: 5
checkpoint_id: 1f18eccd-5c31-63f9-800d-41682a0448ac
checkpoint_step: 13
extraction_rule: MileagePlus number is ([\d-]+)
---

User United MileagePlus number is 8842-1190.

## Provenance

- Source: LangGraph `SqliteSaver` checkpoint store (`checkpoints.sqlite`)
- Thread: `alex-travel` · Turn: 5 · Checkpoint: `1f18eccd-5c31-63f9-800d-41682a0448ac` (step 13)
- Extraction rule: `MileagePlus number is ([\d-]+)`
- Migrated: 2026-08-02T23:49:43.625722+00:00

Migrated with the LangGraph → OKF adapter. See the
[LangGraph persistence docs](https://langchain-ai.github.io/langgraph/concepts/persistence/).
