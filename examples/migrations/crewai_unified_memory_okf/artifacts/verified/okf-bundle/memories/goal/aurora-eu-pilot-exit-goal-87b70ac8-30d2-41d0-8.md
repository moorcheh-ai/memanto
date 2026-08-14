---
type: goal
title: Aurora EU pilot exit goal
description: Migrated from CrewAI unified memory (LanceDB).
resource: crewai://unified-memory/87b70ac8-30d2-41d0-8453-b5d2502383b0
tags:
- crewai
- goal
- deadline
- slo
- scope-goals
- scope-delivery
timestamp: '2026-08-06T00:42:48.237622Z'
x_memanto:
  type: goal
  confidence: 0.98
  source: crewai
crewai:
  schema: unified-memory-lancedb
  id: 87b70ac8-30d2-41d0-8453-b5d2502383b0
  scope: /goals/delivery
  categories:
  - goal
  - deadline
  - slo
  metadata:
    title: Aurora EU pilot exit goal
    memory_type: goal
    deadline: '2026-08-28'
    checkout_p95_ms: 350
    task: Define the pilot release gate
  importance: 0.98
  last_accessed: '2026-08-06T00:42:48.772964Z'
  source: delivery_manager
  private: false
  mapping_basis: metadata.memory_type
  embedding: omitted-derived-data
source_record_sha256: 65b1e398007820d27dc60fbbfdf45d3180c00ab897f99154d1e300c76e053847
redactions: 0
---

Ship the Aurora EU pilot by 2026-08-28 with checkout p95 below 350 milliseconds and zero unresolved severity-one defects.
