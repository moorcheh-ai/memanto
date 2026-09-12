---
type: preference
title: auto split at 50 memories
description: 'OKF layout defaults to split=auto: a type with 50 or fewer memories
  gets one file per memory, a larger type collapses into a single stacked file so
  high-volume agents do not produce thousands of files'
tags:
- okf
- layout
generated:
  by: process:repo-review
  at: '2026-09-01T21:25:52.872185+00:00'
resource: memanto/app/services/okf_export_service.py
x_memanto:
  id: 2f155c2a-e4a4-4e5b-9568-d75c99d269bb
  confidence: 0.8
  provenance: validated
  source: repo-review
  status: active
  updated_at: '2026-09-01T21:25:52.872185+00:00'
  type: preference
---

OKF layout defaults to split=auto: a type with 50 or fewer memories gets one file per memory, a larger type collapses into a single stacked file so high-volume agents do not produce thousands of files.
