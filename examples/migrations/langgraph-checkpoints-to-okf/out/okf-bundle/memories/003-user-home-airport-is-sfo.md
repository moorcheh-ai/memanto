---
type: fact
title: User home airport is SFO.
description: Agent memory migrated from a LangGraph SqliteSaver checkpoint (thread
  'alex-travel', turn 1).
resource: langgraph-checkpoint://alex-travel
tags:
- langgraph
- checkpoint-migration
- alex-travel
- fact
timestamp: '2026-08-02T23:34:15.741373+00:00'
x_memanto:
  type: fact
  confidence: 0.85
  source: langgraph-checkpoints
thread_id: alex-travel
turn: 1
checkpoint_id: 1f18ecaa-cb91-600e-800d-e36cc4d14466
checkpoint_step: 13
extraction_rule: home airport is ([A-Z]{3})
---

User home airport is SFO.

## Provenance

- Source: LangGraph `SqliteSaver` checkpoint store (`checkpoints.sqlite`)
- Thread: `alex-travel` · Turn: 1 · Checkpoint: `1f18ecaa-cb91-600e-800d-e36cc4d14466` (step 13)
- Extraction rule: `home airport is ([A-Z]{3})`
- Migrated: 2026-08-02T23:34:15.968458+00:00

Migrated with the LangGraph → OKF adapter. See the
[LangGraph persistence docs](https://langchain-ai.github.io/langgraph/concepts/persistence/).
