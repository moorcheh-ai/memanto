---
type: instruction
title: Analytics email privacy rule
description: Migrated from CrewAI unified memory (LanceDB).
resource: crewai://unified-memory/85450f4d-2eb3-4f62-bf51-2f1d0bc71c99
tags:
- crewai
- instruction
- privacy
- pii
- scope-instructions
- scope-security
timestamp: '2026-08-06T00:42:47.167153Z'
x_memanto:
  type: instruction
  confidence: 1.0
  source: crewai
crewai:
  schema: unified-memory-lancedb
  id: 85450f4d-2eb3-4f62-bf51-2f1d0bc71c99
  scope: /instructions/security
  categories:
  - instruction
  - privacy
  - pii
  metadata:
    title: Analytics email privacy rule
    memory_type: instruction
    policy: SEC-14
    task: Review analytics event collection
  importance: 1.0
  last_accessed: '2026-08-06T00:42:48.561000Z'
  source: security_auditor
  private: false
  mapping_basis: metadata.memory_type
  embedding: omitted-derived-data
source_record_sha256: 59575c7259f2016ad15e8ce6b1742a5a8e0403277e29f50b51a3383cc6d5dbfb
redactions: 0
---

Never persist raw customer email addresses in analytics events; store a salted irreversible hash and keep the salt in the secret manager.
