---
type: decision
title: Feature flag cache ttl
description: Feature flag cache ttl
tags:
- app:atlas-release-copilot
- scope:app
- source:google-adk
- type:decision
timestamp: '2026-07-21T13:05:03+00:00'
resource: google-adk://sqlite/f622f1697993d042/atlas-release-copilot/app/decision.feature_flag_cache_ttl
x_memanto:
  id: 27aa69e9-1c65-4e9a-a25a-c5ab0e1515ef
  confidence: 0.9
  provenance: imported
  source: tool
  status: active
  type: decision
---

# Feature flag cache ttl

The approved Beacon production feature-flag cache TTL is 6 hours so the flag can be unwound on the same shift.

## Provenance

- Google ADK scope: `app`
- State key: `decision.feature_flag_cache_ttl`
- App: `atlas-release-copilot`

[Audit trail (2 persisted updates)](../../archive/state-history/adk-app-decision-feature-flag-cache-ttl-03ccade6027b.md)

---
[Supporting data]
- OKF source: memories/decision/adk-app-decision-feature-flag-cache-ttl-03ccade6027b.md
- OKF resource: google-adk://sqlite/f622f1697993d042/atlas-release-copilot/app/decision.feature_flag_cache_ttl
- Links: Audit trail (2 persisted updates) -> ../../archive/state-history/adk-app-decision-feature-flag-cache-ttl-03ccade6027b.md
- OKF original source: google-adk
- OKF generated: at=2026-08-01T10:39:52.159236Z; by=memanto-google-adk-okf/1.0.0
- OKF sources: {'id': 'adk-app-decision-feature-flag-cache-ttl-03ccade6027b', 'resource': 'google-adk://sqlite/f622f1697993d042/atlas-release-copilot/app/decision.feature_flag_cache_ttl', 'type': 'google-adk-sqli...
- OKF status: stable
- OKF x_google_adk: app_name=atlas-release-copilot; distinct_values=2; scope=app; state_key=decision.feature_flag_c
...
