---
type: decision
title: PostgreSQL 16 is the current ledger decision
description: Migrated from CrewAI unified memory (LanceDB).
resource: crewai://unified-memory/84b237f2-3188-4230-9776-67ec3c5e4db6
tags:
- crewai
- decision
- database
- current
- scope-decisions
- scope-platform
timestamp: '2026-08-06T00:42:47.012264Z'
x_memanto:
  type: decision
  confidence: 0.96
  source: crewai
crewai:
  schema: unified-memory-lancedb
  id: 84b237f2-3188-4230-9776-67ec3c5e4db6
  scope: /decisions/platform
  categories:
  - decision
  - database
  - current
  metadata:
    title: PostgreSQL 16 is the current ledger decision
    memory_type: decision
    lifecycle_status: active
    supersedes: database-decision-old
    task: Re-evaluate the ledger after the concurrency review
  importance: 0.96
  last_accessed: '2026-08-06T00:42:48.840733Z'
  source: platform_architect
  private: false
  mapping_basis: metadata.memory_type
  embedding: omitted-derived-data
source_record_sha256: 504313e902204b263dc907c8b5b794ca82902f0713ba17bce2c7bf678378a597
redactions: 0
---

The Aurora order ledger must use PostgreSQL 16, replacing SQLite, because concurrent writers and point-in-time recovery are required.
