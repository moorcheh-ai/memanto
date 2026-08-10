---
type: "fact"
title: "Canary deployment is 10 percent for 30 minutes; roll back if errors exceed 1 percent or…"
description: "Canary deployment is 10 percent for 30 minutes; roll back if errors exceed 1 percent or p95 latency exceeds 250 milliseconds"
resource: "http://127.0.0.1:8888/v1/default/banks/beacon-release-copilot/memories/5ba3437c-6320-4503-97c3-92a82a4ada02"
tags: ["demo:hindsight-okf", "project:beacon", "source:hindsight", "hindsight:world"]
sources: [{"author": "process:hindsight", "id": "hindsight-5ba3437c-6320-4503-97c3-92a82a4ada02", "last_modified": "2026-07-25", "resource": "http://127.0.0.1:8888/v1/default/banks/beacon-release-copilot/memories/5ba3437c-6320-4503-97c3-92a82a4ada02", "title": "Hindsight world memory 5ba3437c-6320-4503-97c3-92a82a4ada02"}]
generated: {"at": "2026-07-25T05:03:53.398283Z", "by": "memanto-hindsight-okf/1.0.0"}
status: "stable"
timestamp: "2026-07-25T08:15:00.020000+00:00"
x_memanto: {"confidence": 0.9, "source": "hindsight", "source_id": "5ba3437c-6320-4503-97c3-92a82a4ada02", "status": "active", "type": "fact"}
x_hindsight: {"bank_id": "beacon-release-copilot", "chunk_id": "beacon-release-copilot_session-08-current-truth_0", "context": "Dana signs off the current truth and identifies superseded values", "date": "2026-07-25T08:15:00.020000+00:00", "document_id": "session-08-current-truth", "entities": ["canary simulation", "errors", "p95 latency"], "fact_type": "world", "id": "5ba3437c-6320-4503-97c3-92a82a4ada02", "mentioned_at": "2026-07-25T08:15:00.020000+00:00", "metadata": {"scenario": "beacon-release", "session_id": "session-08-current-truth", "source": "scripted-live-agent-run"}, "proof_count": 1, "state": "valid", "tags": ["demo:hindsight-okf", "project:beacon"]}
---

Canary deployment is 10 percent for 30 minutes; roll back if errors exceed 1 percent or p95 latency exceeds 250 milliseconds

## Source context

Dana signs off the current truth and identifies superseded values

## Provenance

- Hindsight memory ID: `5ba3437c-6320-4503-97c3-92a82a4ada02`
- Hindsight class: `world`
- Curation state: `valid`
- Source document: `session-08-current-truth`
- Linked entities: canary simulation, errors, p95 latency
