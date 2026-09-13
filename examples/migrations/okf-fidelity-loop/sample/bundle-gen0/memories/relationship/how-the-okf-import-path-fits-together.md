---
type: relationship
title: How the OKF import path fits together
description: load_okf_bundle parses a bundle into entries, map_okf turns those entries
  into batch-remember rows, and run_migration imports them in batches of 100. A new
  adapter only has to produce the bundle.
tags:
- migrate
- architecture
generated:
  by: process:repo-review
  at: '2026-09-01T21:25:52.872185+00:00'
resource: memanto/cli/migrate/runner.py
x_memanto:
  id: 477f8272-3f04-4efb-bc40-7fad42c033aa
  confidence: 0.8
  provenance: validated
  source: repo-review
  status: active
  updated_at: '2026-09-01T21:25:52.872185+00:00'
  type: relationship
---

load_okf_bundle parses a bundle into entries, map_okf turns those entries into batch-remember rows, and run_migration imports them in batches of 100. A new adapter only has to produce the bundle.
