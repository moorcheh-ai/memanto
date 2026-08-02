---
type: preference
title: User prefers aisle seat when flying.
description: Agent memory migrated from a LangGraph SqliteSaver checkpoint (thread
  'alex-travel', turn 1).
resource: langgraph-checkpoint://alex-travel
tags:
- langgraph
- checkpoint-migration
- alex-travel
- preference
timestamp: '2026-08-02T23:49:43.587292+00:00'
x_memanto:
  type: preference
  confidence: 0.85
  source: langgraph-checkpoints
thread_id: alex-travel
turn: 1
checkpoint_id: 1f18eccd-5c31-63f9-800d-41682a0448ac
checkpoint_step: 13
extraction_rule: always fly aisle seat
---

User prefers aisle seat when flying.

## Provenance

- Source: LangGraph `SqliteSaver` checkpoint store (`checkpoints.sqlite`)
- Thread: `alex-travel` · Turn: 1 · Checkpoint: `1f18eccd-5c31-63f9-800d-41682a0448ac` (step 13)
- Extraction rule: `always fly aisle seat`
- Migrated: 2026-08-02T23:49:43.621907+00:00

Migrated with the LangGraph → OKF adapter. See the
[LangGraph persistence docs](https://langchain-ai.github.io/langgraph/concepts/persistence/).
