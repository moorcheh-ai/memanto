---
type: error
title: Bundle output is sandboxed to ~/.memanto
description: write_okf_bundle refuses any output_dir outside the agent data directory.
  To write a bundle somewhere else, construct OkfExportService with a custom exports_dir;
  its parent bounds what the service wil
tags:
- okf
- export
generated:
  by: process:repo-review
  at: '2026-09-01T21:25:52.872185+00:00'
resource: memanto/app/utils/validation.py
x_memanto:
  id: 78b38a81-3ca8-47d6-8c73-4133e636c764
  confidence: 0.8
  provenance: validated
  source: repo-review
  status: active
  updated_at: '2026-09-01T21:25:52.872185+00:00'
  type: error
---

write_okf_bundle refuses any output_dir outside the agent data directory. To write a bundle somewhere else, construct OkfExportService with a custom exports_dir; its parent bounds what the service will accept.
