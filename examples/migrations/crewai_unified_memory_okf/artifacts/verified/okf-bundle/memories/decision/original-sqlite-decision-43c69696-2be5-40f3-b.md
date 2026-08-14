---
type: decision
title: Original SQLite decision
description: Migrated from CrewAI unified memory (LanceDB).
resource: crewai://unified-memory/43c69696-2be5-40f3-b92b-77c3bb48ef6c
tags:
- crewai
- decision
- database
- superseded
- scope-decisions
- scope-platform
timestamp: '2026-08-06T00:42:46.551759Z'
x_memanto:
  type: decision
  confidence: 0.45
  source: crewai
crewai:
  schema: unified-memory-lancedb
  id: 43c69696-2be5-40f3-b92b-77c3bb48ef6c
  scope: /decisions/platform
  categories:
  - decision
  - database
  - superseded
  metadata:
    title: Original SQLite decision
    memory_type: decision
    lifecycle_status: superseded
    superseded_by: database-decision-current
    task: Choose the pilot order-ledger database
  importance: 0.45
  last_accessed: '2026-08-06T00:42:48.772964Z'
  source: platform_architect
  private: false
  mapping_basis: metadata.memory_type
  embedding: omitted-derived-data
source_record_sha256: 7d1b184b6be9e0adbdea4ec620295d061441055e75f9d801be64063f71f70a0a
redactions: 0
---

The Aurora pilot originally selected SQLite for the order ledger because the prototype ran on one node.
