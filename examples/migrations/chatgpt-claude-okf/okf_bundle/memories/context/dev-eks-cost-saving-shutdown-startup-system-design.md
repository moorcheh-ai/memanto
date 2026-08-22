---
type: context
title: Dev EKS Cost-Saving Shutdown/Startup System Design
description: 'User is designing an automated shutdown/startup system for a dev EKS
  environment to save costs overnight. Key components: ArgoCD, Karpenter, RDS, and
  general workloads. The chosen approach keeps ArgoC'
tags:
- claude
- assistant-memory
timestamp: '2026-08-06T07:34:53.218765+00:00'
resource: 2f7390c5-d2ac-4fb2-b9f5-8217879c6ed1
x_memanto:
  id: f43f58d4-c6a8-4606-93d7-5d592e70021e
  confidence: 0.95
  provenance: imported
  source: claude
  status: active
  type: context
generated:
  by: memanto-liberate/1.0
  at: '2026-08-06T07:34:53.218765+00:00'
sources:
- resource: conversation 2f7390c5-d2ac-4fb2-b9f5-8217879c6ed1 in a claude data export
  id: claude:2f7390c5-d2ac-4fb2-b9f5-8217879c6ed1
  author: claude
  title: Unspecified request for assistance
---

User is designing an automated shutdown/startup system for a dev EKS environment to save costs overnight. Key components: ArgoCD, Karpenter, RDS, and general workloads. The chosen approach keeps ArgoCD running but disables Auto Sync during shutdown (Option 1), then re-enables it on startup. Lambda orchestrates scaling workloads to zero, Karpenter node cleanup, and RDS stop/start. Step Functions handles orchestration with real readiness polling rather than fixed timers.
