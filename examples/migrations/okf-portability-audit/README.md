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
Issue bodies and comments are split losslessly when necessary, and each chunk
retains the original GitHub URL and a unique portable identifier.

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

### One-command showcase

Run the complete real-data path—archive generation, the official Memanto CLI
dry run, production-code round trip, and lossless audit—with one command:

```bash
python examples/migrations/okf-portability-audit/run_demo.py
```

The command creates a new isolated work directory, prints every executed step,
and leaves an `audit.json` receipt. It performs no cloud writes and needs no API
key. Pass `--show-report` to print the complete JSON instead of only the compact
summary. Results depend on the public issue archive at execution time, the local
generator, Memanto CLI, round-trip and audit code, and their installed dependency
versions.

### Demo video

Watch the [public YouTube showcase](https://youtu.be/25Y2MVPtGzo), with a
checked-in [archival copy](demo/memanto-okf-portability-demo.mp4). It shows the
genuine public archive entering the official Memanto dry run, the
production round trip, the final 27→27 lossless receipt, and a readable OKF
memory. The capture contains real command output and visibly discloses that the
implementation was AI-assisted.

### Mapping and honest savings report

| GitHub source concept | OKF / Memanto representation | Fidelity evidence |
| --- | --- | --- |
| Issue body | `artifact` memory | Lossless chunks with issue URL and timestamp |
| Issue comment | `observation` memory | Lossless chunks with original comment URL and author tag |
| Labels and state | OKF tags | Compared as normalized portable fields |
| Source IDs | `x_memanto.id` | Preserved as origin metadata; destination runtime IDs may change |
| Source URL | `resource` | Used with type/title semantics as a stable identity |

The validated run used 1 issue plus 25 public comments: 27 source records, 27
mapped records, 0 skipped, 27 round-tripped records, 0 removals, and 0 changed
portable fields. Token and retrieval-latency savings are **not applicable** to
this Path C workflow: it audits at-rest portability and makes no invented model
or retrieval baseline. Storage remains human-readable Markdown at both ends.

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

To exercise Memanto's production loader, mapper, automatic type classifier, and
exporter locally before running the audit, choose a new non-existing target:

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

Nodes with a title are matched by their `resource` plus a deterministic hash of
normalized `type` and `title`; records without a title fall back to `resource`,
then `x_memanto.id`. This keeps separately chunked records at one source URL
distinct. The comparison
covers body, title, type, description, resource, links, timestamp, tags, portable
`x_memanto` fields, and unknown frontmatter. Runtime IDs and status may be
reassigned by a destination, so they are excluded. It also normalizes the
reversible description and administrative footer wrapper added by `map_okf`;
unknown supporting data is never hidden. Paths are excluded from fidelity and
reported as moves instead.

The local round-trip demo intentionally processes only the importable
`memories/` section. Export-only context such as `daily-summaries/` and
`sessions/` is outside its scope. It refuses existing or overlapping targets;
the audit also refuses to write its report over or inside either input bundle.

## Tests

```bash
pytest examples/migrations/okf-portability-audit/tests -q
```

The suite covers lossless moves, changed and removed nodes, duplicate IDs,
provenance gaps, exact long-body reconstruction, safe paths, JSON output, and
the CI exit code.
