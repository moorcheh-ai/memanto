---
type: context
title: ruff covers examples/, mypy does not
description: CI runs ruff check and ruff format over the whole repository; only legacy_archive
  is excluded. mypy skips examples/, but ruff does not, so an example with an unused
  import fails the build.
tags:
- ci
- lint
generated:
  by: process:repo-review
  at: '2026-09-01T21:25:52.872185+00:00'
resource: .github/workflows/ci.yml
x_memanto:
  id: ed3db4ec-2f06-4423-b0f2-359903e8cc5b
  confidence: 0.8
  provenance: validated
  source: repo-review
  status: active
  updated_at: '2026-09-01T21:25:52.872185+00:00'
  type: context
---

CI runs ruff check and ruff format over the whole repository; only legacy_archive is excluded. mypy skips examples/, but ruff does not, so an example with an unused import fails the build.
