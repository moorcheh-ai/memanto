---
type: fact
title: x_memanto carries the round trip
description: Memanto-only fields (id, confidence, provenance, source, status and the
  temporal metadata) ride in a namespaced x_memanto frontmatter block. OKF consumers
  ignore unknown keys, so Memanto -> OKF -> Mem
tags:
- okf
- roundtrip
generated:
  by: process:repo-review
  at: '2026-09-01T21:25:52.872185+00:00'
resource: memanto/app/services/okf_export_service.py
x_memanto:
  id: bc3d6dc3-52bf-47e3-bf34-6f5254a784b3
  confidence: 0.8
  provenance: validated
  source: repo-review
  status: active
  updated_at: '2026-09-01T21:25:52.872185+00:00'
  type: fact
---

Memanto-only fields (id, confidence, provenance, source, status and the temporal metadata) ride in a namespaced x_memanto frontmatter block. OKF consumers ignore unknown keys, so Memanto -> OKF -> Memanto keeps them.
