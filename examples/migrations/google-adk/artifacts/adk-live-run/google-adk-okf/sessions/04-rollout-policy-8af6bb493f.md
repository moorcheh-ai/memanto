---
{
  "generated": {
    "at": "2026-08-01T09:43:04.409881Z",
    "by": "memanto-google-adk-okf/1.0.0"
  },
  "status": "stable",
  "timestamp": "2026-07-16T16:10:02Z",
  "title": "Google ADK session 04-rollout-policy",
  "type": "session",
  "x_google_adk": {
    "app_name": "atlas-release-copilot",
    "events": 2,
    "session_id": "04-rollout-policy",
    "user_id": "dana"
  }
}
---

# Google ADK session 04-rollout-policy

- App: `atlas-release-copilot`
- User: `dana`
- First persisted event: `2026-07-16T16:10:01Z`
- Last persisted event: `2026-07-16T16:10:02Z`
- Captured: `2026-08-01T09:43:04.409881Z`

> Context-only transcript. Memanto's OKF importer scopes imports to `memories/`.

## 2026-07-16T16:10:01Z — user

Decision: start at a 10 percent canary for 30 minutes. Promote only below 1 percent errors and below 250 ms p95. Roll back immediately if either threshold is breached.

## 2026-07-16T16:10:02Z — release_copilot

The canary and rollback decision is in the durable runbook state.

State updates: `app:decision.canary_and_rollback`
