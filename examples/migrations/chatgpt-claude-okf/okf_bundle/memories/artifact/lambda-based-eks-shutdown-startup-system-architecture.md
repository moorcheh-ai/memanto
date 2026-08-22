---
type: artifact
title: Lambda-based EKS Shutdown/Startup System Architecture
description: 'Lambda package structure: one entry point (lambda_function.py) dispatching
  discrete single-action calls (disable_auto_sync, scale_down_dev, check_rds_available,
  etc.). k8s_auth.py generates IAM auth t'
tags:
- claude
- assistant-memory
timestamp: '2026-08-06T07:34:53.218765+00:00'
resource: 2f7390c5-d2ac-4fb2-b9f5-8217879c6ed1
x_memanto:
  id: f12c5b81-ff4b-4802-a181-0124cf1c2de3
  confidence: 0.92
  provenance: imported
  source: claude
  status: active
  type: artifact
generated:
  by: memanto-liberate/1.0
  at: '2026-08-06T07:34:53.218765+00:00'
sources:
- id: claude:2f7390c5-d2ac-4fb2-b9f5-8217879c6ed1
  author: claude
  title: Unspecified request for assistance
---

Lambda package structure: one entry point (lambda_function.py) dispatching discrete single-action calls (disable_auto_sync, scale_down_dev, check_rds_available, etc.). k8s_auth.py generates IAM auth tokens to talk to Kubernetes API directly via Python kubernetes client (no kubectl/aws-cli binary needed). config.py hard-excludes kube-system, karpenter, and argocd namespaces from scaling. Step Functions state machine (statemachine.asl.json) polls every 20-30s for real readiness. IAM policy covers RDS/EKS/S3. Lambda IAM role also needs mapping into each cluster's RBAC via aws-auth ConfigMap or EKS access entry.
