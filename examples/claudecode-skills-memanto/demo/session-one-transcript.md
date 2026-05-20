Decision: Use PostgreSQL for durable project state because the team already runs Postgres in production.
Constraint: API changes must preserve backwards-compatible response fields.
Preference: Keep service code dependency-light and avoid new runtime frameworks for small routes.

$ pytest tests/test_api.py

Artifact: Added pagination notes to docs/api-pagination.md for the next skill run.
