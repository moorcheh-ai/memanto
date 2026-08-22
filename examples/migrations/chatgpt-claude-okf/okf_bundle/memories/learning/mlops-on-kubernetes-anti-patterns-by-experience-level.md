---
type: learning
title: MLOps on Kubernetes anti-patterns by experience level
description: 'Beginner anti-patterns: (1) Omitting CPU/memory resource requests causing
  node overcommit. (2) Rebuilding container images per environment instead of promoting
  immutable images. (3) Shipping straight '
tags:
- claude
- assistant-memory
timestamp: '2026-08-21T06:54:21.323047+00:00'
resource: 60bf29e2-4c44-418c-aa94-aa0af1c868cf
x_memanto:
  id: 3d19927e-824b-4a9f-8177-ee0cf55a2f32
  confidence: 0.93
  provenance: imported
  source: claude
  status: active
  type: learning
generated:
  by: memanto-liberate/1.0
  at: '2026-08-21T06:54:21.323047+00:00'
sources:
- id: claude:60bf29e2-4c44-418c-aa94-aa0af1c868cf
  author: claude
  title: 'MLOps on Kubernetes: comprehensive analysis across resources'
---

Beginner anti-patterns: (1) Omitting CPU/memory resource requests causing node overcommit. (2) Rebuilding container images per environment instead of promoting immutable images. (3) Shipping straight from notebooks — depends on one machine state, one kernel session, undocumented pip installs. Experienced anti-patterns: (1) Deploying new models to 100% traffic without shadow/canary phase, especially for high-risk decisions. (2) GPU quota hoarding — one unconstrained grid search can consume 100% org GPU capacity for days without Kueue enforcement. (3) Insufficient documentation of hyperparameter search and ML context. (4) Monitoring without closed-loop retraining — drift detection must programmatically trigger versioned retraining workflows, not just alert humans.
