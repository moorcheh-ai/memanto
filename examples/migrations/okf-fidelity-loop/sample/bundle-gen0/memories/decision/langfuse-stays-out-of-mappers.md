---
type: decision
title: Langfuse stays out of MAPPERS
description: 'Langfuse is deliberately absent from the MAPPERS registry: its rows
  are observability events, not memories, so one incident collapses into a single
  grouped payload instead of mapping row-for-row.'
tags:
- migrate
- langfuse
generated:
  by: process:repo-review
  at: '2026-09-01T21:25:52.872185+00:00'
resource: memanto/cli/migrate/mappers.py
x_memanto:
  id: 406bf96b-99b7-494c-b79b-996169d9a87c
  confidence: 0.8
  provenance: validated
  source: repo-review
  status: active
  updated_at: '2026-09-01T21:25:52.872185+00:00'
  type: decision
---

Langfuse is deliberately absent from the MAPPERS registry: its rows are observability events, not memories, so one incident collapses into a single grouped payload instead of mapping row-for-row.
