---
type: learning
title: Staging database preflight
description: Staging database preflight
tags:
- app:atlas-release-copilot
- scope:app
- source:google-adk
- type:learning
timestamp: '2026-07-13T11:45:01+00:00'
resource: google-adk://sqlite/53fe4b9a40eeb169/atlas-release-copilot/app/learning.staging_database_preflight
x_memanto:
  id: 67d4f67c-5ba1-43a7-aa31-723acae4288b
  confidence: 0.9
  provenance: imported
  source: tool
  status: active
  type: learning
---

# Staging database preflight

The first Beacon staging migration failed because the PostgreSQL 16 pg_trgm extension was missing. After enabling pg_trgm it succeeded in 3 minutes 42 seconds with 185 ms p95 latency. The runbook now requires a pg_trgm preflight.

## Provenance

- Google ADK scope: `app`
- State key: `learning.staging_database_preflight`
- App: `atlas-release-copilot`

---
[Supporting data]
- OKF source: memories\learning\adk-app-learning-staging-database-preflight-10ccf95d697a.md
- OKF resource: google-adk://sqlite/53fe4b9a40eeb169/atlas-release-copilot/app/learning.staging_database_preflight
- OKF original source: google-adk
- OKF generated: at=2026-07-31T16:47:49.413615Z; by=memanto-google-adk-okf/1.0.0
- OKF sources: {'id': 'adk-app-learning-staging-database-preflight-10ccf95d697a', 'resource': 'google-adk://sqlite/53fe4b9a40eeb169/atlas-release-copilot/app/learning.staging_database_preflight', 'type': 'google-...
- OKF status: stable
- OKF x_google_adk: app_name=atlas-release-copilot; distinct_values=1; scope=app; state_key=learning.staging_database_preflight; state_updates=1
