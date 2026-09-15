---
type: "MCP component"
title: "Memanto OKF Loader"
description: "Imports Markdown documents from the memories directory."
resource: "memory://knowledge-graph/entities/Memanto%20OKF%20Loader"
tags: ["mcp-memory", "mcp-entity", "entity-type-component"]
x_memanto:
  type: "artifact"
  source: "mcp-memory-server"
  confidence: 1.0
mcp_memory:
  schema_version: 1
  original_line: 3
  entity_name: "Memanto OKF Loader"
  entity_type: "component"
  observation_count: 2
  outgoing_relation_count: 0
  incoming_relation_count: 1
---

# Memanto OKF Loader

## Entity

- **Type:** `component`
- **Source line:** 3

## Observations

1. Imports Markdown documents from the memories directory.
2. Preserves unknown OKF frontmatter in a Supporting data footer.

## Relationships

### Outgoing

_None._

### Incoming

- [Portable OKF Bundle](portable-okf-bundle.md) → `is consumed by`

## Lossless MCP source

The block below preserves the exact entity record and all of its outgoing relation records for reconstruction.

```json mcp-memory-source
{
  "entity": {
    "line": 3,
    "record": {
      "type": "entity",
      "name": "Memanto OKF Loader",
      "entityType": "component",
      "observations": [
        "Imports Markdown documents from the memories directory.",
        "Preserves unknown OKF frontmatter in a Supporting data footer."
      ]
    }
  },
  "outgoing_relations": []
}
```
