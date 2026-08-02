---
type: fact
title: User name is Alex Rivera.
description: Agent memory migrated from a LangGraph SqliteSaver checkpoint (thread
  'alex-travel', turn 1).
resource: langgraph-checkpoint://alex-travel
tags:
- langgraph
- checkpoint-migration
- alex-travel
- fact
timestamp: '2026-08-02T23:34:15.741308+00:00'
x_memanto:
  type: fact
  confidence: 0.85
  source: langgraph-checkpoints
thread_id: alex-travel
turn: 1
checkpoint_id: 1f18ecaa-cb91-600e-800d-e36cc4d14466
checkpoint_step: 13
extraction_rule: I'm ([A-Z][a-z]+ [A-Z][a-z]+)
---

User name is Alex Rivera.

## Provenance

- Source: LangGraph `SqliteSaver` checkpoint store (`checkpoints.sqlite`)
- Thread: `alex-travel` · Turn: 1 · Checkpoint: `1f18ecaa-cb91-600e-800d-e36cc4d14466` (step 13)
- Extraction rule: `I'm ([A-Z][a-z]+ [A-Z][a-z]+)`
- Migrated: 2026-08-02T23:34:15.967040+00:00

Migrated with the LangGraph → OKF adapter. See the
[LangGraph persistence docs](https://langchain-ai.github.io/langgraph/concepts/persistence/).
