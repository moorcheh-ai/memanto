---
type: event
title: 'Incident INC-441 resolved: pgbouncer pool exhaustion after a migration spike....'
description: 'Incident INC-441 resolved: pgbouncer pool exhaustion after a migration
  spike....'
tags:
- source:chroma
- events
- session:week-4-incident
generated:
  by: process:chroma
  at: '2026-06-22T10:00:00Z'
resource: chroma://agent_long_term_memory/chroma-incident
x_memanto:
  type: event
  confidence: 0.86
  provenance: explicit_statement
  source: chroma
  id: chroma:chroma-incident
chroma_id: chroma-incident
session_id: week-4-incident
sources:
- chroma
---

Incident INC-441 resolved: pgbouncer pool exhaustion after a migration spike. Root cause was max_client_conn=100.
