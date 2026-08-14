---
type: learning
title: AUR-218 idempotency remediation
description: Migrated from CrewAI unified memory (LanceDB).
tags:
- crewai
- learning
- remediation
- billing
- scope-learnings
- scope-billing
timestamp: '2026-08-06T00:42:47.621417+00:00'
resource: crewai://unified-memory/b380bc30-d008-4fee-b554-8e390ec2a3ac
x_memanto:
  id: d1d626f9-dfce-495b-a6ef-6233acf11184
  confidence: 0.93
  provenance: imported
  source: crewai
  status: active
  type: learning
---

Migrated from CrewAI unified memory (LanceDB).

All invoice creation calls now require the event UUID as an idempotency key, and the database enforces a unique constraint on it.

---
[Supporting data]
- OKF source: memories/learning/aur-218-idempotency-remediation-b380bc30-d008-4fee-b.md
- OKF resource: crewai://unified-memory/b380bc30-d008-4fee-b554-8e390ec2a3ac
- OKF crewai: schema=unified-memory-lancedb; id=b380bc30-d008-4fee-b554-8e390ec2a3ac; scope=/learnings/billing; categories=['learning', 'remediation', 'billing']; metadata={'title': 'AUR-218 idempotency remediat...
- OKF source_record_sha256: 57a64e347612d1b04d42efd34dc226b31ba573353404ed2cabc0d7c75236d6d5
- OKF redactions: 0
