---
type: instruction
title: Analytics email privacy rule
description: Migrated from CrewAI unified memory (LanceDB).
tags:
- crewai
- instruction
- privacy
- pii
- scope-instructions
- scope-security
timestamp: '2026-08-06T00:42:47.167153+00:00'
resource: crewai://unified-memory/85450f4d-2eb3-4f62-bf51-2f1d0bc71c99
x_memanto:
  id: 57b58174-d88e-4f9d-9127-3907974d4acb
  confidence: 1
  provenance: imported
  source: crewai
  status: active
  type: instruction
---

Migrated from CrewAI unified memory (LanceDB).

Never persist raw customer email addresses in analytics events; store a salted irreversible hash and keep the salt in the secret manager.

---
[Supporting data]
- OKF source: memories\instruction\analytics-email-privacy-rule-85450f4d-2eb3-4f62-b.md
- OKF resource: crewai://unified-memory/85450f4d-2eb3-4f62-bf51-2f1d0bc71c99
- OKF crewai: schema=unified-memory-lancedb; id=85450f4d-2eb3-4f62-bf51-2f1d0bc71c99; scope=/instructions/security; categories=['instruction', 'privacy', 'pii']; metadata={'title': 'Analytics email privacy rule'...
- OKF source_record_sha256: 59575c7259f2016ad15e8ce6b1742a5a8e0403277e29f50b51a3383cc6d5dbfb
- OKF redactions: 0
