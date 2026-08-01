---
type: decision
title: Canary and rollback
description: Canary and rollback
tags:
- app:atlas-release-copilot
- scope:app
- source:google-adk
- type:decision
timestamp: '2026-07-16T16:10:02+00:00'
resource: google-adk://sqlite/53fe4b9a40eeb169/atlas-release-copilot/app/decision.canary_and_rollback
x_memanto:
  id: 8aebb1cd-865e-4a6a-a969-7d4f3a7d6b4c
  confidence: 0.9
  provenance: imported
  source: tool
  status: active
  type: decision
---

# Canary and rollback

Beacon starts at a 10 percent canary for 30 minutes. Promote only while errors remain below 1 percent and p95 latency remains below 250 ms; otherwise roll back immediately.

## Provenance

- Google ADK scope: `app`
- State key: `decision.canary_and_rollback`
- App: `atlas-release-copilot`

---
[Supporting data]
- OKF source: memories\decision\adk-app-decision-canary-and-rollback-6e8237827ebe.md
- OKF resource: google-adk://sqlite/53fe4b9a40eeb169/atlas-release-copilot/app/decision.canary_and_rollback
- OKF original source: google-adk
- OKF generated: at=2026-07-31T16:47:49.413615Z; by=memanto-google-adk-okf/1.0.0
- OKF sources: {'id': 'adk-app-decision-canary-and-rollback-6e8237827ebe', 'resource': 'google-adk://sqlite/53fe4b9a40eeb169/atlas-release-copilot/app/decision.canary_and_rollback', 'type': 'google-adk-sqlite-sta...
- OKF status: stable
- OKF x_google_adk: app_name=atlas-release-copilot; distinct_values=1; scope=app; state_key=decision.canary_and_rollback; state_updates=1
