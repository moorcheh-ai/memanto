---
{
  "description": "Beacon starts at a 10 percent canary for 30 minutes. Promote only while errors remain below 1 percent and p95 latency remains below 250 ms; otherwise roll back immediately.",
  "generated": {
    "at": "2026-08-01T09:43:04.409881Z",
    "by": "memanto-google-adk-okf/1.0.0"
  },
  "resource": "google-adk://sqlite/9d4e01eee56aefea/atlas-release-copilot/app/decision.canary_and_rollback",
  "sources": [
    {
      "id": "adk-app-decision-canary-and-rollback-6e8237827ebe",
      "resource": "google-adk://sqlite/9d4e01eee56aefea/atlas-release-copilot/app/decision.canary_and_rollback",
      "type": "google-adk-sqlite-state"
    }
  ],
  "status": "stable",
  "tags": [
    "app:atlas-release-copilot",
    "scope:app",
    "source:google-adk",
    "type:decision"
  ],
  "timestamp": "2026-07-16T16:10:02Z",
  "title": "Canary and rollback",
  "type": "decision",
  "x_google_adk": {
    "app_name": "atlas-release-copilot",
    "distinct_values": 1,
    "scope": "app",
    "session_id": null,
    "state_key": "decision.canary_and_rollback",
    "state_updates": 1,
    "user_id": null
  },
  "x_memanto": {
    "confidence": 0.9,
    "id": "adk-app-decision-canary-and-rollback-6e8237827ebe",
    "provenance": "imported",
    "source": "google-adk",
    "status": "active",
    "type": "decision"
  }
}
---

# Canary and rollback

Beacon starts at a 10 percent canary for 30 minutes. Promote only while errors remain below 1 percent and p95 latency remains below 250 ms; otherwise roll back immediately.

## Provenance

- Google ADK scope: `app`
- State key: `decision.canary_and_rollback`
- App: `atlas-release-copilot`
