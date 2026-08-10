---
type: "fact"
title: "Dana decided to start Beacon with 10% canary rollout for 30 minutes, promoting only if…"
description: "Dana decided to start Beacon with 10% canary rollout for 30 minutes, promoting only if error rate < 1% and p95 latency < 250ms, with immediate rollback on threshold breach | When:…"
resource: "http://127.0.0.1:8888/v1/default/banks/beacon-release-copilot/memories/3e3caf33-5810-4b86-b204-193dd543336d"
tags: ["demo:hindsight-okf", "project:beacon", "source:hindsight", "hindsight:world"]
sources: [{"author": "process:hindsight", "id": "hindsight-3e3caf33-5810-4b86-b204-193dd543336d", "last_modified": "2026-07-25", "resource": "http://127.0.0.1:8888/v1/default/banks/beacon-release-copilot/memories/3e3caf33-5810-4b86-b204-193dd543336d", "title": "Hindsight world memory 3e3caf33-5810-4b86-b204-193dd543336d"}]
generated: {"at": "2026-07-25T05:03:53.398283Z", "by": "memanto-hindsight-okf/1.0.0"}
status: "stable"
timestamp: "2026-07-25T05:02:08.265667+00:00"
x_memanto: {"confidence": 0.9, "source": "hindsight", "source_id": "3e3caf33-5810-4b86-b204-193dd543336d", "status": "active", "type": "fact"}
x_hindsight: {"bank_id": "beacon-release-copilot", "chunk_id": "beacon-release-copilot_session-04-rollout-decision_0", "consolidated_at": "2026-07-25T05:02:08.265667+00:00", "context": "The team chooses a canary and rollback policy", "date": "2026-07-16T16:10:00+00:00", "document_id": "session-04-rollout-decision", "entities": ["p95 latency", "Beacon", "canary", "Dana", "error rate", "rollback"], "fact_type": "world", "id": "3e3caf33-5810-4b86-b204-193dd543336d", "mentioned_at": "2026-07-16T16:10:00+00:00", "metadata": {"scenario": "beacon-release", "session_id": "session-04-rollout-decision", "source": "scripted-live-agent-run"}, "proof_count": 1, "state": "valid", "tags": ["demo:hindsight-okf", "project:beacon"]}
---

Dana decided to start Beacon with 10% canary rollout for 30 minutes, promoting only if error rate < 1% and p95 latency < 250ms, with immediate rollback on threshold breach | When: 2026-07-16 | Involving: Dana (user)

## Source context

The team chooses a canary and rollback policy

## Provenance

- Hindsight memory ID: `3e3caf33-5810-4b86-b204-193dd543336d`
- Hindsight class: `world`
- Curation state: `valid`
- Source document: `session-04-rollout-decision`
- Linked entities: p95 latency, Beacon, canary, Dana, error rate, rollback
