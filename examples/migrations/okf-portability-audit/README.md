# OKF portability audit

Prove that an agent-memory migration preserved what matters before deleting the
source. This example compares an original and a migrated Open Knowledge Format
(OKF) bundle, using Memanto's production loader and no network access or API key.

It reports:

- added, removed, and changed memory nodes;
- the exact portable fields that changed;
- file moves that did not alter content;
- duplicate stable identities; and
- missing provenance in either bundle.

The audit is read-only and deterministic, so its JSON mode can be used as a CI
gate while Markdown gives a reviewer-friendly migration receipt.

## Reproduce with real public data

The included generator fetches a genuine GitHub issue archive and every public
comment through the official API, then emits a human-readable OKF bundle. It
does not use a hand-written fixture or require a GitHub token for public repos.

```bash
python examples/migrations/okf-portability-audit/github_issue_to_okf.py \
  moorcheh-ai/memanto 1609 ./github-memory
python examples/migrations/okf-portability-audit/roundtrip_demo.py \
  ./github-memory ./round-tripped
python examples/migrations/okf-portability-audit/okf_audit.py \
  ./github-memory ./round-tripped --fail-on-change
```

At the time this showcase was validated, issue #1609 contained one issue and 25
comments. The long issue body was split at paragraph boundaries to respect the
Memanto content limit, producing 27 real memory nodes. The importer/exporter
round trip kept all 27 portable records with no removals or changed fields.

## Run the included lossless example

From the repository root:

```bash
python examples/migrations/okf-portability-audit/okf_audit.py \
  examples/migrations/okf-portability-audit/sample/before \
  examples/migrations/okf-portability-audit/sample/after
```

The example intentionally renames a file while preserving the memory's stable
`resource`. The result passes fidelity, records the move separately, and matches
the checked-in [`EXPECTED.md`](EXPECTED.md) receipt.

To exercise Memanto's production loader, mapper, and exporter locally before
running the audit:

```bash
python examples/migrations/okf-portability-audit/roundtrip_demo.py \
  examples/migrations/okf-portability-audit/sample/before ./round-tripped
python examples/migrations/okf-portability-audit/okf_audit.py \
  examples/migrations/okf-portability-audit/sample/before ./round-tripped
```

## Audit a real migration

Export the source, migrate it, and export the destination:

```bash
memanto memory export --okf --agent source-agent --output ./before
memanto migrate okf ./before --agent destination-agent
memanto memory export --okf --agent destination-agent --output ./after
python examples/migrations/okf-portability-audit/okf_audit.py ./before ./after \
  --format json --output audit.json --fail-on-change
```

`--fail-on-change` returns exit code 1 only when a source node or portable field
was lost or changed, or when duplicate identities make the result ambiguous.
Additions and file moves remain visible but do not fail a migration because the
destination may already contain memories and OKF layout is intentionally free.

## Identity and fidelity rules

Nodes are matched by `resource`, then a deterministic hash of normalized `type`
and `title`, then `x_memanto.id` when no semantic identity exists. The comparison
covers body, title, type, description, resource, timestamp, tags, portable
`x_memanto` fields, and unknown frontmatter. Runtime IDs and status may be
reassigned by a destination, so they are excluded. It also normalizes the
reversible description and administrative footer wrapper added by `map_okf`;
unknown supporting data is never hidden. Paths are excluded from fidelity and
reported as moves instead.

## Tests

```bash
pytest examples/migrations/okf-portability-audit/tests -q
```

The suite covers lossless moves, changed and removed nodes, duplicate IDs,
provenance gaps, JSON output, and the CI exit code.
