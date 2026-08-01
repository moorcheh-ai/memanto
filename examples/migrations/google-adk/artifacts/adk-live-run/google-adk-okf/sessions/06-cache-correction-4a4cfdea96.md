---
{
  "generated": {
    "at": "2026-08-01T09:43:04.409881Z",
    "by": "memanto-google-adk-okf/1.0.0"
  },
  "status": "stable",
  "timestamp": "2026-07-21T13:05:03Z",
  "title": "Google ADK session 06-cache-correction",
  "type": "session",
  "x_google_adk": {
    "app_name": "atlas-release-copilot",
    "events": 3,
    "session_id": "06-cache-correction",
    "user_id": "dana"
  }
}
---

# Google ADK session 06-cache-correction

- App: `atlas-release-copilot`
- User: `dana`
- First persisted event: `2026-07-21T13:05:01Z`
- Last persisted event: `2026-07-21T13:05:03Z`
- Captured: `2026-08-01T09:43:04.409881Z`

> Context-only transcript. Memanto's OKF importer scopes imports to `memories/`.

## 2026-07-21T13:05:01Z — release_copilot

The draft runbook says the feature-flag cache TTL is 24 hours.

State updates: `app:decision.feature_flag_cache_ttl`

## 2026-07-21T13:05:02Z — user

That draft is wrong. The approved production TTL is 6 hours, not 24, so we can unwind the flag on the same shift.

## 2026-07-21T13:05:03Z — release_copilot

Corrected: six hours is now the approved current value.

State updates: `app:decision.feature_flag_cache_ttl`
