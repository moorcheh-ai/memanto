---
{
  "description": "The first Beacon staging migration failed because the PostgreSQL 16 pg_trgm extension was missing. After enabling pg_trgm it succeeded in 3 minutes 42 seconds with 185 ms p95 latency. The runbook now ",
  "generated": {
    "at": "2026-07-31T16:47:49.413615Z",
    "by": "memanto-google-adk-okf/1.0.0"
  },
  "resource": "google-adk://sqlite/53fe4b9a40eeb169/atlas-release-copilot/app/learning.staging_database_preflight",
  "sources": [
    {
      "id": "adk-app-learning-staging-database-preflight-10ccf95d697a",
      "resource": "google-adk://sqlite/53fe4b9a40eeb169/atlas-release-copilot/app/learning.staging_database_preflight",
      "type": "google-adk-sqlite-state"
    }
  ],
  "status": "stable",
  "tags": [
    "app:atlas-release-copilot",
    "scope:app",
    "source:google-adk",
    "type:learning"
  ],
  "timestamp": "2026-07-13T11:45:01Z",
  "title": "Staging database preflight",
  "type": "learning",
  "x_google_adk": {
    "app_name": "atlas-release-copilot",
    "distinct_values": 1,
    "scope": "app",
    "session_id": null,
    "state_key": "learning.staging_database_preflight",
    "state_updates": 1,
    "user_id": null
  },
  "x_memanto": {
    "confidence": 0.9,
    "id": "adk-app-learning-staging-database-preflight-10ccf95d697a",
    "provenance": "imported",
    "source": "google-adk",
    "status": "active",
    "type": "learning"
  }
}
---

# Staging database preflight

The first Beacon staging migration failed because the PostgreSQL 16 pg_trgm extension was missing. After enabling pg_trgm it succeeded in 3 minutes 42 seconds with 185 ms p95 latency. The runbook now requires a pg_trgm preflight.

## Provenance

- Google ADK scope: `app`
- State key: `learning.staging_database_preflight`
- App: `atlas-release-copilot`
