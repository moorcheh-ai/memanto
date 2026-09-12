---
type: observation
title: Unmapped OKF types defer to auto-classification
description: map_okf leaves type=None when OKF's free-form type has no Memanto slot,
  deferring to server-side auto-classification, and records the original OKF type
  in the supporting-data footer instead.
tags:
- okf
- types
generated:
  by: process:repo-review
  at: '2026-09-01T21:25:52.872185+00:00'
resource: memanto/cli/migrate/mappers.py
x_memanto:
  id: cb9f6de0-7e3e-48ff-bbdf-a2b065489d3e
  confidence: 0.8
  provenance: validated
  source: repo-review
  status: active
  updated_at: '2026-09-01T21:25:52.872185+00:00'
  type: observation
---

map_okf leaves type=None when OKF's free-form type has no Memanto slot, deferring to server-side auto-classification, and records the original OKF type in the supporting-data footer instead.
