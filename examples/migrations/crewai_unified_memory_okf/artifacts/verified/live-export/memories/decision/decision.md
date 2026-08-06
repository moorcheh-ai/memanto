---
type: decision
title: Original SQLite decision
description: Migrated from CrewAI unified memory (LanceDB).
tags:
- crewai
- decision
- database
- superseded
- scope-decisions
- scope-platform
timestamp: '2026-08-06T00:42:46.551759+00:00'
resource: crewai://unified-memory/43c69696-2be5-40f3-b92b-77c3bb48ef6c
x_memanto:
  id: c438c5ce-dc4c-4377-8310-29f0de98b4b6
  confidence: 0.45
  provenance: imported
  source: crewai
  status: active
  type: decision
---

Migrated from CrewAI unified memory (LanceDB).

The Aurora pilot originally selected SQLite for the order ledger because the prototype ran on one node.

---
[Supporting data]
- OKF source: memories\decision\original-sqlite-decision-43c69696-2be5-40f3-b.md
- OKF resource: crewai://unified-memory/43c69696-2be5-40f3-b92b-77c3bb48ef6c
- OKF crewai: schema=unified-memory-lancedb; id=43c69696-2be5-40f3-b92b-77c3bb48ef6c; scope=/decisions/platform; categories=['decision', 'database', 'superseded']; metadata={'title': 'Original SQLite decision', ...
- OKF source_record_sha256: 7d1b184b6be9e0adbdea4ec620295d061441055e75f9d801be64063f71f70a0a
- OKF redactions: 0

<!-- okf-entry -->
---
type: decision
title: PostgreSQL 16 is the current ledger decision
description: Migrated from CrewAI unified memory (LanceDB).
tags:
- crewai
- decision
- database
- current
- scope-decisions
- scope-platform
timestamp: '2026-08-06T00:42:47.012264+00:00'
resource: crewai://unified-memory/84b237f2-3188-4230-9776-67ec3c5e4db6
x_memanto:
  id: 5b1d8b23-fcca-48f0-9a61-04e95cdf8312
  confidence: 0.96
  provenance: imported
  source: crewai
  status: active
  type: decision
---

Migrated from CrewAI unified memory (LanceDB).

The Aurora order ledger must use PostgreSQL 16, replacing SQLite, because concurrent writers and point-in-time recovery are required.

---
[Supporting data]
- OKF source: memories\decision\postgresql-16-is-the-current-ledger-decision-84b237f2-3188-4230-9.md
- OKF resource: crewai://unified-memory/84b237f2-3188-4230-9776-67ec3c5e4db6
- OKF crewai: schema=unified-memory-lancedb; id=84b237f2-3188-4230-9776-67ec3c5e4db6; scope=/decisions/platform; categories=['decision', 'database', 'current']; metadata={'title': 'PostgreSQL 16 is the current l...
- OKF source_record_sha256: 504313e902204b263dc907c8b5b794ca82902f0713ba17bce2c7bf678378a597
- OKF redactions: 0
