---
type: learning
title: AUR-218 idempotency remediation
description: Migrated from CrewAI unified memory (LanceDB).
resource: crewai://unified-memory/b380bc30-d008-4fee-b554-8e390ec2a3ac
tags:
- crewai
- learning
- remediation
- billing
- scope-learnings
- scope-billing
timestamp: '2026-08-06T00:42:47.621417Z'
x_memanto:
  type: learning
  confidence: 0.93
  source: crewai
crewai:
  schema: unified-memory-lancedb
  id: b380bc30-d008-4fee-b554-8e390ec2a3ac
  scope: /learnings/billing
  categories:
  - learning
  - remediation
  - billing
  metadata:
    title: AUR-218 idempotency remediation
    memory_type: learning
    incident_id: AUR-218
    task: Prevent recurrence of duplicate invoices
  importance: 0.93
  last_accessed: '2026-08-06T00:42:48.703233Z'
  source: reliability_engineer
  private: false
  mapping_basis: metadata.memory_type
  embedding: omitted-derived-data
source_record_sha256: 57a64e347612d1b04d42efd34dc226b31ba573353404ed2cabc0d7c75236d6d5
redactions: 0
---

All invoice creation calls now require the event UUID as an idempotency key, and the database enforces a unique constraint on it.
