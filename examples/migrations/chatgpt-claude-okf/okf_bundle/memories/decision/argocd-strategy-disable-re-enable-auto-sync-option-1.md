---
type: decision
title: 'ArgoCD Strategy: Disable/Re-enable Auto Sync (Option 1)'
description: 'Chose Option 1: disable ArgoCD Auto Sync during shutdown and re-enable
  on startup. This requires no changes to the Git repo and works purely from Lambda.
  Option 2 (ignoreDifferences on /spec/replicas)'
tags:
- claude
- assistant-memory
generated:
  by: process:claude
  at: '2026-08-06T07:34:53.218765+00:00'
resource: 2f7390c5-d2ac-4fb2-b9f5-8217879c6ed1
x_memanto:
  id: 5ba497ae-fe54-4c92-8a31-9ce976cc5e15
  confidence: 0.95
  provenance: imported
  source: claude
  status: active
  type: decision
---

Chose Option 1: disable ArgoCD Auto Sync during shutdown and re-enable on startup. This requires no changes to the Git repo and works purely from Lambda. Option 2 (ignoreDifferences on /spec/replicas) was noted as an alternative if Auto Sync should stay on permanently. The ignoreDifferences approach can be layered on later.
