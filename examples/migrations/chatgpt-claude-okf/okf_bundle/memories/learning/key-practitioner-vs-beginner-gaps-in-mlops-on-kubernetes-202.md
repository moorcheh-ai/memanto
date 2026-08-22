---
type: learning
title: Key practitioner vs beginner gaps in MLOps on Kubernetes (2026)
description: 1. Kubeflow Trainer v2 replaced six CRDs (PyTorchJob, TFJob, MPIJob,
  etc.) with one unified TrainJob API; beginner tutorials still teach old APIs. 2.
  Seldon Core moved to Business Source License in ea
tags:
- claude
- assistant-memory
timestamp: '2026-08-21T06:54:21.323047+00:00'
resource: 60bf29e2-4c44-418c-aa94-aa0af1c868cf
x_memanto:
  id: ac8b2a72-b5f6-47c9-8f6b-0858b5020dfc
  confidence: 0.95
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

1. Kubeflow Trainer v2 replaced six CRDs (PyTorchJob, TFJob, MPIJob, etc.) with one unified TrainJob API; beginner tutorials still teach old APIs. 2. Seldon Core moved to Business Source License in early 2024 — production use requires commercial license; pre-2024 tutorials miss this. 3. GPU utilization averages 52% without proper scheduling; Kueue raises it to 60-85%. 4. KEDA with vllm num_requests_waiting metric is the correct LLM autoscaling approach; CPU-based autoscaling is wrong for GPU-bound inference. 5. Kubernetes is the wrong choice for single models with modest predictable traffic — managed endpoints (SageMaker, Vertex AI) are simpler and cheaper in that case.
