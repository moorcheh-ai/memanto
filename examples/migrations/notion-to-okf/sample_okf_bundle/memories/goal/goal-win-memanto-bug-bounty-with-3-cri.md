---
type: goal
title: "Goal: win Memanto bug bounty with 3+ Critical/High severity bugs"
timestamp: "2026-06-20T07:00:00+00:00"
tags:
  - goal
  - bounty
  - security
  - notion-db:research-notes
x_memanto:
  type: goal
  source: notion
  confidence: 0.9
  provenance: imported
---

Goal: submit PR #784 with at minimum 3 reproducible High-severity bugs in Memanto's temporal recall pipeline. Found bugs: (1) naive/aware datetime mismatch in 12 locations, (2) recall/as-of has no query field causing timeline amnesia, (3) 100-memory silent cap in _fetch_all_memories. All submitted with reproducible failing tests and actual fixes.

---
[Supporting data]
- Source: notion:d0e1f2a3-b4c5-6789-3456-890123456789
- Notion database: Research Notes
- Notion URL: https://notion.so/d0e1f2a3b4c5
- Notion status: In Progress
- Priority: High
- Last edited: 2026-06-24T09:45:00+00:00
- Source created_at: 2026-06-20T07:00:00+00:00
