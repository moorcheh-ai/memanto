---
type: "MCP project"
title: "MCP Memory Server Adapter"
description: "Transforms the official MCP Memory Server JSONL knowledge graph into portable OKF Markdown."
resource: "memory://knowledge-graph/entities/MCP%20Memory%20Server%20Adapter"
tags: ["mcp-memory", "mcp-entity", "entity-type-project"]
x_memanto:
  type: "artifact"
  source: "mcp-memory-server"
  confidence: 1.0
mcp_memory:
  schema_version: 1
  original_line: 1
  entity_name: "MCP Memory Server Adapter"
  entity_type: "project"
  observation_count: 5
  outgoing_relation_count: 3
  incoming_relation_count: 0
---

# MCP Memory Server Adapter

## Entity

- **Type:** `project`
- **Source line:** 1

## Observations

1. Transforms the official MCP Memory Server JSONL knowledge graph into portable OKF Markdown.
2. Chosen after a repository search found no existing MCP Memory migration submission on 2026-07-27.
3. Uses one OKF document per entity and embeds exact source records for lossless reconstruction.
4. Runs offline with no third-party Python dependencies.
5. The initial LangGraph direction was discarded after active migration PRs were found.

## Relationships

### Outgoing

- `reads` → [Official MCP Memory Server](official-mcp-memory-server.md)
- `produces` → [Portable OKF Bundle](portable-okf-bundle.md)
- `targets` → [Memanto Bounty 1609](memanto-bounty-1609.md)

### Incoming

_None._

## Lossless MCP source

The block below preserves the exact entity record and all of its outgoing relation records for reconstruction.

```json mcp-memory-source
{
  "entity": {
    "line": 1,
    "record": {
      "type": "entity",
      "name": "MCP Memory Server Adapter",
      "entityType": "project",
      "observations": [
        "Transforms the official MCP Memory Server JSONL knowledge graph into portable OKF Markdown.",
        "Chosen after a repository search found no existing MCP Memory migration submission on 2026-07-27.",
        "Uses one OKF document per entity and embeds exact source records for lossless reconstruction.",
        "Runs offline with no third-party Python dependencies.",
        "The initial LangGraph direction was discarded after active migration PRs were found."
      ]
    }
  },
  "outgoing_relations": [
    {
      "line": 6,
      "record": {
        "type": "relation",
        "from": "MCP Memory Server Adapter",
        "to": "Official MCP Memory Server",
        "relationType": "reads"
      }
    },
    {
      "line": 7,
      "record": {
        "type": "relation",
        "from": "MCP Memory Server Adapter",
        "to": "Portable OKF Bundle",
        "relationType": "produces"
      }
    },
    {
      "line": 9,
      "record": {
        "type": "relation",
        "from": "MCP Memory Server Adapter",
        "to": "Memanto Bounty 1609",
        "relationType": "targets"
      }
    }
  ]
}
```
