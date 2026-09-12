---
type: fact
title: Production MLOps real-world scale benchmarks and tool decisions
description: 'Uber Michelangelo: 400 active ML projects, 5000+ models, 10M real-time
  predictions/second at peak. Built 100+ custom CRDs. Solved GPU stranded compute
  via a federation layer (Michelangelo Job Controll'
tags:
- claude
- assistant-memory
timestamp: '2026-08-21T06:54:21.323047+00:00'
resource: 60bf29e2-4c44-418c-aa94-aa0af1c868cf
x_memanto:
  id: 865f405d-188b-44cb-a3a1-fd8ad943e9c4
  confidence: 0.92
  provenance: imported
  source: claude
  status: active
  type: fact
generated:
  by: memanto-liberate/1.0
  at: '2026-08-21T06:54:21.323047+00:00'
sources:
- resource: conversation 60bf29e2-4c44-418c-aa94-aa0af1c868cf in a claude data export
  id: claude:60bf29e2-4c44-418c-aa94-aa0af1c868cf
  author: claude
  title: 'MLOps on Kubernetes: comprehensive analysis across resources'
---

Uber Michelangelo: 400 active ML projects, 5000+ models, 10M real-time predictions/second at peak. Built 100+ custom CRDs. Solved GPU stranded compute via a federation layer (Michelangelo Job Controller) — essentially Kueue's model reinvented in-house. Spotify Hendrix: merged 5 separate ML products into one platform with unified Python SDK; ML engineer adoption grew from 16% to 71%, serving 600+ ML practitioners. Feast break-even point: 3-5 production models or 2+ ML teams sharing features. 2026 consensus production stack: vLLM + Kueue + KServe + Ray. For models >70B parameters: llm-d for distributed inference via prefill/decode disaggregation.
