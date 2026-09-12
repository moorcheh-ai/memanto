---
type: fact
title: Only memories/ is importable
description: 'An OKF bundle nests importable memories under memories/. The sibling
  daily-summaries/, sessions/ and metrics/ folders are export-only context and are
  skipped on import, so re-importing a bundle never '
tags:
- okf
- import
generated:
  by: process:repo-review
  at: '2026-09-01T21:25:52.872185+00:00'
resource: memanto/cli/migrate/okf_loader.py
x_memanto:
  id: d5ef1f6c-544f-4b19-b0df-c9d3fd55a30e
  confidence: 0.8
  provenance: validated
  source: repo-review
  status: active
  updated_at: '2026-09-01T21:25:52.872185+00:00'
  type: fact
---

An OKF bundle nests importable memories under memories/. The sibling daily-summaries/, sessions/ and metrics/ folders are export-only context and are skipped on import, so re-importing a bundle never re-ingests its own logs.
