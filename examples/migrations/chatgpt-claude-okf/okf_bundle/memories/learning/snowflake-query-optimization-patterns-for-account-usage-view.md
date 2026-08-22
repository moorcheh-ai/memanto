---
type: learning
title: Snowflake query optimization patterns for ACCOUNT_USAGE views
description: 'Key optimization principles for Snowflake ACCOUNT_USAGE queries: 1)
  Avoid SELECT DISTINCT as a band-aid for fan-out join issues. 2) Always add time-bound
  filters (e.g. DATEADD(day, -30, CURRENT_TIMEST'
tags:
- claude
- assistant-memory
timestamp: '2026-07-31T11:08:51.471094+00:00'
resource: d9692fc2-a237-49d9-a0b7-a568198c89d9
x_memanto:
  id: f6747333-972a-45b8-94a6-f95834e34134
  confidence: 0.95
  provenance: imported
  source: claude
  status: active
  type: learning
generated:
  by: memanto-liberate/1.0
  at: '2026-07-31T11:08:51.471094+00:00'
sources:
- id: claude:d9692fc2-a237-49d9-a0b7-a568198c89d9
  author: claude
  title: Optimizing Snowflake grants and user activity query
---

Key optimization principles for Snowflake ACCOUNT_USAGE queries: 1) Avoid SELECT DISTINCT as a band-aid for fan-out join issues. 2) Always add time-bound filters (e.g. DATEADD(day, -30, CURRENT_TIMESTAMP())) on large views like QUERY_HISTORY and LOGIN_HISTORY to reduce bytes scanned. 3) Use QUALIFY ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...) = 1 instead of ORDER BY ... LIMIT 1 inside subqueries for latest-row-per-user patterns. 4) Use CTEs to define repeated literal values (e.g. username) as a single source of truth. 5) ACCOUNT_USAGE views have 45min-3hr latency and are not real-time.
