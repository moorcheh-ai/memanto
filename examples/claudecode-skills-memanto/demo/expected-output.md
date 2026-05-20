# Offline Demo Output

Command:

```bash
./run_offline_demo.sh
```

Expected output:

```text
Stored 5 memory item(s) for skill `grill-with-docs`.
- decision: Decision: Use PostgreSQL for durable project state because the team already runs Postgres in production.
- instruction: Constraint: API changes must preserve backwards-compatible response fields.
- preference: Preference: Keep service code dependency-light and avoid new runtime frameworks for small routes.
- artifact: Artifact: Added pagination notes to docs/api-pagination.md for the next skill run.
- learning: Useful command for grill-with-docs: pytest tests/test_api.py

Memanto context for this skill run:
Task: add pagination tests

Apply these remembered engineering constraints when relevant:
1. [learning; skill:grill-with-docs; tags: claudecode-skills, grill-with-docs, api-pagination.md, api, design, pagination] Useful command for grill-with-docs: pytest tests/test_api.py
2. [artifact; skill:grill-with-docs; tags: claudecode-skills, grill-with-docs, api-pagination.md, api, design, pagination] Artifact: Added pagination notes to docs/api-pagination.md for the next skill run.
3. [preference; skill:grill-with-docs; tags: claudecode-skills, grill-with-docs, api-pagination.md, api, design, pagination] Preference: Keep service code dependency-light and avoid new runtime frameworks for small routes.
4. [instruction; skill:grill-with-docs; tags: claudecode-skills, grill-with-docs, api-pagination.md, api, design, pagination] Constraint: API changes must preserve backwards-compatible response fields.
5. [decision; skill:grill-with-docs; tags: claudecode-skills, grill-with-docs, api-pagination.md, api, design, pagination] Decision: Use PostgreSQL for durable project state because the team already runs Postgres in production.
```

Optional manifest check:

```bash
python skills_manifest.py /tmp/mattpocock-skills --format markdown
```

This prints a table of skills from the real `.claude-plugin/plugin.json`
manifest, including names such as `grill-with-docs`, `tdd`, `diagnose`, and
`handoff`.
