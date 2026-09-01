---
type: artifact
title: okf-entry separates stacked documents
description: Stacked OKF files hold several documents separated by the <!-- okf-entry
  --> sentinel, so a body containing its own --- rule cannot be mistaken for a document
  boundary.
tags:
- okf
- format
generated:
  by: process:repo-review
  at: '2026-09-01T21:25:52.872185+00:00'
resource: memanto/app/services/okf_export_service.py
x_memanto:
  id: 1910baa3-1f88-470d-a7b7-e86980b07920
  confidence: 0.8
  provenance: validated
  source: repo-review
  status: active
  updated_at: '2026-09-01T21:25:52.872185+00:00'
  type: artifact
---

Stacked OKF files hold several documents separated by the <!-- okf-entry --> sentinel, so a body containing its own --- rule cannot be mistaken for a document boundary.
