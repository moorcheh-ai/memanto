---
type: "MCP artifact"
title: "Portable OKF Bundle"
description: "Keeps entity observations readable as Markdown."
resource: "memory://knowledge-graph/entities/Portable%20OKF%20Bundle"
tags: ["mcp-memory", "mcp-entity", "entity-type-artifact"]
x_memanto:
  type: "artifact"
  source: "mcp-memory-server"
  confidence: 1.0
mcp_memory:
  schema_version: 1
  original_line: 5
  entity_name: "Portable OKF Bundle"
  entity_type: "artifact"
  observation_count: 3
  outgoing_relation_count: 1
  incoming_relation_count: 1
---

# Portable OKF Bundle

## Entity

- **Type:** `artifact`
- **Source line:** 5

## Observations

1. Keeps entity observations readable as Markdown.
2. Keeps graph relations navigable as typed links.
3. Copies the original memory.jsonl outside memories so Memanto does not re-ingest it.

## Relationships

### Outgoing

- `is consumed by` → [Memanto OKF Loader](memanto-okf-loader.md)

### Incoming

- [MCP Memory Server Adapter](mcp-memory-server-adapter.md) → `produces`

## Lossless MCP source

The block below preserves the exact entity record and all of its outgoing relation records for reconstruction.

```json mcp-memory-source
{
  "entity": {
    "line": 5,
    "record": {
      "type": "entity",
      "name": "Portable OKF Bundle",
      "entityType": "artifact",
      "observations": [
        "Keeps entity observations readable as Markdown.",
        "Keeps graph relations navigable as typed links.",
        "Copies the original memory.jsonl outside memories so Memanto does not re-ingest it."
      ]
    }
  },
  "outgoing_relations": [
    {
      "line": 8,
      "record": {
        "type": "relation",
        "from": "Portable OKF Bundle",
        "to": "Memanto OKF Loader",
        "relationType": "is consumed by"
      }
    }
  ]
}
```
