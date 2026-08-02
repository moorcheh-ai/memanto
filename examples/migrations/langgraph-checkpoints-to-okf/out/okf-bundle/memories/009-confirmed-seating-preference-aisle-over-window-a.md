---
type: preference
title: 'Confirmed seating preference: aisle over window, always.'
description: Agent memory migrated from a LangGraph SqliteSaver checkpoint (thread
  'alex-travel', turn 5).
resource: langgraph-checkpoint://alex-travel
tags:
- langgraph
- checkpoint-migration
- alex-travel
- preference
timestamp: '2026-08-02T23:34:15.754100+00:00'
x_memanto:
  type: preference
  confidence: 0.85
  source: langgraph-checkpoints
thread_id: alex-travel
turn: 5
checkpoint_id: 1f18ecaa-cb91-600e-800d-e36cc4d14466
checkpoint_step: 13
extraction_rule: aisle over window, always
---

Confirmed seating preference: aisle over window, always.

## Provenance

- Source: LangGraph `SqliteSaver` checkpoint store (`checkpoints.sqlite`)
- Thread: `alex-travel` · Turn: 5 · Checkpoint: `1f18ecaa-cb91-600e-800d-e36cc4d14466` (step 13)
- Extraction rule: `aisle over window, always`
- Migrated: 2026-08-02T23:34:15.972474+00:00

Migrated with the LangGraph → OKF adapter. See the
[LangGraph persistence docs](https://langchain-ai.github.io/langgraph/concepts/persistence/).
