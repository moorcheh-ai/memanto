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
  ],
  "source_file": {
    "encoding": "base64",
    "sha256": "bf97e55e76a5e835df64b7374a5d413877cbab2616852ef59a77df78a8e9ee5f",
    "bytes": "eyJ0eXBlIjoiZW50aXR5IiwibmFtZSI6Ik1DUCBNZW1vcnkgU2VydmVyIEFkYXB0ZXIiLCJlbnRpdHlUeXBlIjoicHJvamVjdCIsIm9ic2VydmF0aW9ucyI6WyJUcmFuc2Zvcm1zIHRoZSBvZmZpY2lhbCBNQ1AgTWVtb3J5IFNlcnZlciBKU09OTCBrbm93bGVkZ2UgZ3JhcGggaW50byBwb3J0YWJsZSBPS0YgTWFya2Rvd24uIiwiQ2hvc2VuIGFmdGVyIGEgcmVwb3NpdG9yeSBzZWFyY2ggZm91bmQgbm8gZXhpc3RpbmcgTUNQIE1lbW9yeSBtaWdyYXRpb24gc3VibWlzc2lvbiBvbiAyMDI2LTA3LTI3LiIsIlVzZXMgb25lIE9LRiBkb2N1bWVudCBwZXIgZW50aXR5IGFuZCBlbWJlZHMgZXhhY3Qgc291cmNlIHJlY29yZHMgZm9yIGxvc3NsZXNzIHJlY29uc3RydWN0aW9uLiIsIlJ1bnMgb2ZmbGluZSB3aXRoIG5vIHRoaXJkLXBhcnR5IFB5dGhvbiBkZXBlbmRlbmNpZXMuIiwiVGhlIGluaXRpYWwgTGFuZ0dyYXBoIGRpcmVjdGlvbiB3YXMgZGlzY2FyZGVkIGFmdGVyIGFjdGl2ZSBtaWdyYXRpb24gUFJzIHdlcmUgZm91bmQuIl19CnsidHlwZSI6ImVudGl0eSIsIm5hbWUiOiJPZmZpY2lhbCBNQ1AgTWVtb3J5IFNlcnZlciIsImVudGl0eVR5cGUiOiJ0b29sIiwib2JzZXJ2YXRpb25zIjpbIlN0b3JlcyBlbnRpdGllcyBhbmQgcmVsYXRpb25zIGFzIG5ld2xpbmUtZGVsaW1pdGVkIEpTT04uIiwiVGhlIHBhY2thZ2UgdmVyc2lvbiBwaW5uZWQgZm9yIHRoaXMgcmVwcm9kdWNpYmxlIHNob3djYXNlIGlzIDIwMjYuNy40LiJdfQp7InR5cGUiOiJlbnRpdHkiLCJuYW1lIjoiTWVtYW50byBPS0YgTG9hZGVyIiwiZW50aXR5VHlwZSI6ImNvbXBvbmVudCIsIm9ic2VydmF0aW9ucyI6WyJJbXBvcnRzIE1hcmtkb3duIGRvY3VtZW50cyBmcm9tIHRoZSBtZW1vcmllcyBkaXJlY3RvcnkuIiwiUHJlc2VydmVzIHVua25vd24gT0tGIGZyb250bWF0dGVyIGluIGEgU3VwcG9ydGluZyBkYXRhIGZvb3Rlci4iXX0KeyJ0eXBlIjoiZW50aXR5IiwibmFtZSI6Ik1lbWFudG8gQm91bnR5IDE2MDkiLCJlbnRpdHlUeXBlIjoiYm91bnR5Iiwib2JzZXJ2YXRpb25zIjpbIlJld2FyZHMgYSBjb21wZWxsaW5nIHJlcHJvZHVjaWJsZSBtaWdyYXRpb24gc2hvd2Nhc2UuIiwiUGF0aCBCIGdpdmVzIGhpZ2hlc3QgZW5naW5lZXJpbmcgdmFsdWUgdG8gYSBuZXcgc291cmNlIGFkYXB0ZXIuIl19CnsidHlwZSI6ImVudGl0eSIsIm5hbWUiOiJQb3J0YWJsZSBPS0YgQnVuZGxlIiwiZW50aXR5VHlwZSI6ImFydGlmYWN0Iiwib2JzZXJ2YXRpb25zIjpbIktlZXBzIGVudGl0eSBvYnNlcnZhdGlvbnMgcmVhZGFibGUgYXMgTWFya2Rvd24uIiwiS2VlcHMgZ3JhcGggcmVsYXRpb25zIG5hdmlnYWJsZSBhcyB0eXBlZCBsaW5rcy4iLCJDb3BpZXMgdGhlIG9yaWdpbmFsIG1lbW9yeS5qc29ubCBvdXRzaWRlIG1lbW9yaWVzIHNvIE1lbWFudG8gZG9lcyBub3QgcmUtaW5nZXN0IGl0LiJdfQp7InR5cGUiOiJyZWxhdGlvbiIsImZyb20iOiJNQ1AgTWVtb3J5IFNlcnZlciBBZGFwdGVyIiwidG8iOiJPZmZpY2lhbCBNQ1AgTWVtb3J5IFNlcnZlciIsInJlbGF0aW9uVHlwZSI6InJlYWRzIn0KeyJ0eXBlIjoicmVsYXRpb24iLCJmcm9tIjoiTUNQIE1lbW9yeSBTZXJ2ZXIgQWRhcHRlciIsInRvIjoiUG9ydGFibGUgT0tGIEJ1bmRsZSIsInJlbGF0aW9uVHlwZSI6InByb2R1Y2VzIn0KeyJ0eXBlIjoicmVsYXRpb24iLCJmcm9tIjoiUG9ydGFibGUgT0tGIEJ1bmRsZSIsInRvIjoiTWVtYW50byBPS0YgTG9hZGVyIiwicmVsYXRpb25UeXBlIjoiaXMgY29uc3VtZWQgYnkifQp7InR5cGUiOiJyZWxhdGlvbiIsImZyb20iOiJNQ1AgTWVtb3J5IFNlcnZlciBBZGFwdGVyIiwidG8iOiJNZW1hbnRvIEJvdW50eSAxNjA5IiwicmVsYXRpb25UeXBlIjoidGFyZ2V0cyJ9"
  }
}
```
