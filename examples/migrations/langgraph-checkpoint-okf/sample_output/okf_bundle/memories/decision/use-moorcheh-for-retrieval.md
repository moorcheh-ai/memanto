---
type: decision
title: Use Moorcheh for retrieval
description: Use Moorcheh as the retrieval backend for the agent memory prototype
  because the zero-indexing latency test beat vector search.
tags:
- langgraph
- thread:founder-os-agent
- channel:memories
- session:s02_launch
- architecture
- retrieval
timestamp: '2026-07-28T14:31:00Z'
resource: langgraph://thread/founder-os-agent/checkpoint/1f18bbec-93c4-6cf7-800a-2b05fc4d6f23/channel/memories/3
x_memanto:
  confidence: 0.93
  provenance: imported_langgraph_checkpoint
  source: langgraph-checkpoint
  type: decision
---

Use Moorcheh as the retrieval backend for the agent memory prototype because the zero-indexing latency test beat vector search.

## LangGraph provenance

Source path: `1f18bbec-93c4-6cf7-800a-2b05fc4d6f23:memories/3`

```json
{
  "langgraph_extra": {
    "evidence_prompt": "Decision: use Moorcheh as retrieval backend for the agent memory prototype after the zero-indexing latency test beat vector search.",
    "source_session": "s02_launch"
  },
  "source_id": "lg-mem-004",
  "source_path": "1f18bbec-93c4-6cf7-800a-2b05fc4d6f23:memories/3"
}
```
