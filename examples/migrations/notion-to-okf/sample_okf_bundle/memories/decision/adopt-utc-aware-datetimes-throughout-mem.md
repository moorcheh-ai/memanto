---
type: decision
title: "Adopt UTC-aware datetimes throughout memory write pipeline"
timestamp: "2026-06-24T09:00:00+00:00"
tags:
  - bug-fix
  - datetime
  - decision
  - notion-db:project-decisions
x_memanto:
  type: decision
  source: notion
  confidence: 0.9
  provenance: imported
---

Decision: replace all datetime.utcnow() calls with datetime.now(timezone.utc) in memory_write_service.py and core.py (12 locations). Root cause: naive timestamps written to storage, timezone-aware timestamps used in temporal filters — silent TypeError causing temporal filters to fail open.

---
[Supporting data]
- Source: notion:f6a7b8c9-d0e1-2345-f012-456789012345
- Notion database: Project Decisions
- Notion URL: https://notion.so/f6a7b8c9d0e1
- Notion status: Decided
- Priority: High
- Last edited: 2026-06-24T09:30:00+00:00
- Source created_at: 2026-06-24T09:00:00+00:00
