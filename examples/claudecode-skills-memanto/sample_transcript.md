# Sample skill transcript

Skill: /grill-with-docs
Task: Design the billing import pipeline

Decision: importer retries should happen in the queue worker, not in the HTTP
handler. This keeps request latency predictable and makes retry state visible in
job metadata.

Codebase quirk: billing tests must use fixture account IDs. Do not mention real
customer names in tests, docs, commit messages, or pull request text.

Preference: keep generated handoff notes short and focused on files changed,
commands run, and remaining review risks.
