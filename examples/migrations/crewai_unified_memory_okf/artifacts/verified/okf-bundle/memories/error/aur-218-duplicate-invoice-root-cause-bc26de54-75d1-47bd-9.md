---
type: error
title: AUR-218 duplicate invoice root cause
description: Migrated from CrewAI unified memory (LanceDB).
resource: crewai://unified-memory/bc26de54-75d1-47bd-938b-d185650124b8
tags:
- crewai
- error
- incident
- billing
- scope-errors
- scope-billing
timestamp: '2026-08-06T00:42:47.444020Z'
x_memanto:
  type: error
  confidence: 0.94
  source: crewai
crewai:
  schema: unified-memory-lancedb
  id: bc26de54-75d1-47bd-938b-d185650124b8
  scope: /errors/billing
  categories:
  - error
  - incident
  - billing
  metadata:
    title: AUR-218 duplicate invoice root cause
    memory_type: error
    incident_id: AUR-218
    affected_records: 3
    task: Complete the invoice incident review
  importance: 0.94
  last_accessed: '2026-08-06T00:42:48.703233Z'
  source: reliability_engineer
  private: false
  mapping_basis: metadata.memory_type
  embedding: omitted-derived-data
source_record_sha256: a7be2788257ff3728f8e69e30cb9f4eaa0fc4bc349c9e0eae340c856fdbe68e7
redactions: 0
---

Invoice retry incident AUR-218 duplicated three invoices because the worker retried after a timeout without an idempotency key.
