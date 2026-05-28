# Sample /grill-with-docs Transcript

User asked for a billing webhook design that can survive provider retries,
duplicate events, and partial outages.

- Decision: use an outbox table for billing webhook side effects instead of
  calling downstream services inline.
- Constraint: every webhook handler must be idempotent by provider event id.
- Preference: keep provider-specific payload parsing in adapter modules and keep
  domain services provider-agnostic.
- Artifact: created an ADR draft describing event ingestion, outbox processing,
  and retry observability.
- Learned: the current codebase already has a job runner, so webhook replay
  should reuse that queue instead of adding a second worker system.
