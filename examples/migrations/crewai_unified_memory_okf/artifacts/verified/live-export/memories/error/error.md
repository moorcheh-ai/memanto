---
type: error
title: AUR-218 duplicate invoice root cause
description: Migrated from CrewAI unified memory (LanceDB).
tags:
- crewai
- error
- incident
- billing
- scope-errors
- scope-billing
timestamp: '2026-08-06T00:42:47.444020+00:00'
resource: crewai://unified-memory/bc26de54-75d1-47bd-938b-d185650124b8
x_memanto:
  id: 95866e88-bd85-4961-b4ec-a7660d82e434
  confidence: 0.94
  provenance: imported
  source: crewai
  status: active
  type: error
---

Migrated from CrewAI unified memory (LanceDB).

Invoice retry incident AUR-218 duplicated three invoices because the worker retried after a timeout without an idempotency key.

---
[Supporting data]
- OKF source: memories\error\aur-218-duplicate-invoice-root-cause-bc26de54-75d1-47bd-9.md
- OKF resource: crewai://unified-memory/bc26de54-75d1-47bd-938b-d185650124b8
- OKF crewai: schema=unified-memory-lancedb; id=bc26de54-75d1-47bd-938b-d185650124b8; scope=/errors/billing; categories=['error', 'incident', 'billing']; metadata={'title': 'AUR-218 duplicate invoice root cause'...
- OKF source_record_sha256: a7be2788257ff3728f8e69e30cb9f4eaa0fc4bc349c9e0eae340c856fdbe68e7
- OKF redactions: 0
