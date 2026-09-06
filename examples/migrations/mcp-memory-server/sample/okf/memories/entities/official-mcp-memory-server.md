---
type: "MCP tool"
title: "Official MCP Memory Server"
description: "Stores entities and relations as newline-delimited JSON."
resource: "memory://knowledge-graph/entities/Official%20MCP%20Memory%20Server"
tags: ["mcp-memory", "mcp-entity", "entity-type-tool"]
x_memanto:
  type: "artifact"
  source: "mcp-memory-server"
  confidence: 1.0
mcp_memory:
  schema_version: 1
  original_line: 2
  entity_name: "Official MCP Memory Server"
  entity_type: "tool"
  observation_count: 2
  outgoing_relation_count: 0
  incoming_relation_count: 1
---

# Official MCP Memory Server

## Entity

- **Type:** `tool`
- **Source line:** 2

## Observations

1. Stores entities and relations as newline-delimited JSON.
2. The package version pinned for this reproducible showcase is 2026.7.4.

## Relationships

### Outgoing

_None._

### Incoming

- [MCP Memory Server Adapter](mcp-memory-server-adapter.md) → `reads`

## Lossless MCP source

The block below preserves the exact entity record and all of its outgoing relation records for reconstruction.

```json mcp-memory-source
{
  "entity": {
    "line": 2,
    "record": {
      "type": "entity",
      "name": "Official MCP Memory Server",
      "entityType": "tool",
      "observations": [
        "Stores entities and relations as newline-delimited JSON.",
        "The package version pinned for this reproducible showcase is 2026.7.4."
      ]
    }
  },
  "outgoing_relations": []
}
```
