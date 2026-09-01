---
type: learning
title: Round trips must be idempotent
description: 'Repeated OKF round trips used to stack one [Supporting data] footer
  per cycle, because _attach_footer appended unconditionally to content that already
  carried the previous pass''s footer. Stripping it '
tags:
- okf
- roundtrip
- fidelity
generated:
  by: process:repo-review
  at: '2026-09-01T21:25:52.872185+00:00'
resource: memanto/cli/migrate/mappers.py
x_memanto:
  id: fe8a712a-de71-448a-9973-c335071d1244
  confidence: 0.8
  provenance: validated
  source: repo-review
  status: active
  updated_at: '2026-09-01T21:25:52.872185+00:00'
  type: learning
---

Repeated OKF round trips used to stack one [Supporting data] footer per cycle, because _attach_footer appended unconditionally to content that already carried the previous pass's footer. Stripping it first makes the loop converge.
