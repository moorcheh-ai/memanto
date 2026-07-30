# n8n execution memory → portable OKF

An n8n workflow makes decisions, observes outcomes, and accumulates operational
history, but that memory is normally trapped inside its execution database.
This example turns selected node outputs from **real n8n executions** into a
human-readable, git-friendly Open Knowledge Format (OKF) bundle that Memanto can
import.

The included LeadOps run is a concrete story: a workflow evaluates inbound
leads, explains each score, chooses a hot/warm/cold route, and sets a follow-up
deadline. The migration preserves those decisions and their provenance without
copying the lead's email address.

## Why this path is different

- It adds a reusable migration path for an unsupported source: n8n execution
  history.
- It consumes the official n8n public API shape produced by
  `GET /api/v1/executions?includeData=true`.
- It uses Memanto's shipped `OkfExportService`, OKF loader, and `map_okf`
  round-trip mapper.
- It is allow-list based. Only fields declared in `mapping.yaml` can become
  memory, so credentials, headers, emails, and unrelated node payloads stay out.
- Every memory has a stable ID derived from its n8n source coordinate:
  workflow, execution, node, run, output, and item.
- Repeated conversions of identical inputs are byte-for-byte deterministic.
- Publishing is atomic: a complete, validated bundle replaces the old output
  only after the round trip succeeds.

## Fifteen-minute quick start

Requirements:

- Python 3.10–3.12
- n8n 2.x only if exporting your own execution history
- A Moorcheh API key only for the final live import into Memanto

From the repository root:

```bash
python -m venv .venv
.venv/Scripts/pip install -r examples/migrations/n8n_executions/requirements.txt
.venv/Scripts/python -m examples.migrations.n8n_executions.run_demo
```

On macOS/Linux, replace `.venv/Scripts/` with `.venv/bin/`.

The one-command demo:

1. reads the export of actual n8n runs produced by `run_source_demo.py`;
2. selects the configured node and fields;
3. builds the OKF bundle with Memanto's own writer;
4. reloads it through Memanto's OKF loader and mapper;
5. verifies stable IDs and record counts; and
6. runs the same golden questions against the source-derived memories and the
   imported Memanto rows.

Expected headline result:

```text
3 n8n executions → 3 decision memories → 3 OKF documents
round trip: valid
selected-field semantic fingerprints: preserved
golden recall parity: 3/3 (100%)
```

Recorded evidence in this directory comes from n8n `2.32.6`, workflow
`nuMIHADKIMhTbCFc`, execution IDs `4`, `5`, and `6`. The official Memanto
command:

```bash
memanto migrate okf examples/migrations/n8n_executions/sample-okf --dry-run
```

reported `3` OKF nodes, `3` mapped memories, `0` skipped, and a
`decision: 3` type breakdown. See `dry-run-evidence.md` and
`memanto-dry-run-preview.json` for the committed proof.

The committed storage report compares measured files rather than inventing a
provider baseline: `32,763` bytes of full n8n execution JSON become `4,802`
bytes across eight readable OKF Markdown files, a reduction of `27,961` bytes
(`85.34%`) after the allow-list intentionally removes headers, emails, workflow
code, and unrelated runtime state. Provider cost, token, and latency savings are
reported as unavailable (`null`).

## Reproduce the source runs

Import `leadops-demo.n8n.json` into a local n8n 2.x instance, publish it, and
send the three committed scenarios through its production webhook:

```bash
python -m examples.migrations.n8n_executions.run_source_demo
```

The inputs deliberately span all routing outcomes: Atlas Fleet is hot, Beacon
Studio is warm, and Cedar Hobby is cold. They use fictional identities and are
safe to inspect, but the resulting execution records are created by n8n itself;
the committed source export is not hand-authored to resemble n8n.

## Export your own n8n runs

Create an n8n API key, keep it outside version control, and run:

```bash
export N8N_API_KEY="..."
python -m examples.migrations.n8n_executions.export_n8n_executions \
  --base-url http://localhost:5679 \
  --workflow-id YOUR_WORKFLOW_ID \
  --status success \
  --output n8n-executions.private.json
```

PowerShell equivalent:

```powershell
$env:N8N_API_KEY = "..."
python -m examples.migrations.n8n_executions.export_n8n_executions `
  --base-url http://localhost:5679 `
  --workflow-id YOUR_WORKFLOW_ID `
  --status success `
  --output n8n-executions.private.json
```

Treat the raw export as private. It can contain every item that passed through
the workflow. Review `mapping.yaml`, then convert it:

```bash
python -m examples.migrations.n8n_executions.adapter \
  n8n-executions.private.json \
  --mapping examples/migrations/n8n_executions/mapping.yaml \
  --output my-n8n-okf
```

Input can be:

- the n8n public API envelope (`{"data": [...], "nextCursor": "..."}`);
- an array of full execution objects;
- one full execution object; or
- a directory of JSON files in any of those shapes.

## Mapping table

| n8n concept | Source coordinate | Memanto / OKF target |
| --- | --- | --- |
| Workflow identity | `workflowId`, `workflowData.name` | Markdown provenance and `resource` |
| Source actor | n8n execution API | `x_memanto.source: tool`; concrete n8n identity stays in provenance, tags, and resource |
| Execution identity | `id` | stable `x_memanto.id` and provenance |
| Execution time | `stoppedAt` or `startedAt` | OKF `timestamp` |
| Execution status | `status` | Markdown provenance |
| Selected node item | `data.resultData.runData[<node>]...json` | one OKF memory |
| Lead routing outcome | `qualification.route` | `decision` memory and tag |
| Score | `qualification.score` | content only; provenance confidence stays fixed at `1.0` |
| Reasons / next action | configured dotted paths | readable Markdown fields |
| Unselected payload | any path absent from `fields` | **not migrated** |

`mapping.yaml` supports multiple node mappings. Each declares:

- `node`: the exact n8n node name;
- `memory_type`: one of Memanto's 13 memory types;
- `title`: a dotted-path template;
- `fields`: the only payload fields permitted in the memory body;
- optional templated `tags`; and
- either fixed `confidence` or a normalized `confidence_path`.

## Fidelity and privacy evidence

Each output contains:

- `migration-manifest.json`: source-file hashes, mapping hash, source count,
  memory count, per-type breakdown, skipped reasons, and every source coordinate;
- `round-trip-report.json`: OKF loader/mapper counts and stable-ID parity;
- `metrics/savings-report.json`: measured source-vs-readable-Markdown bytes,
  with unavailable provider metrics left null;
- `recall-parity-report.json`: per-question before/after golden recall results;
- `memories/<type>/*.md`: the inspectable portable memory; and
- normal Memanto indexes and aggregate metrics.

The manifest also stores one SHA-256 fingerprint per selected semantic memory
record. The round-trip validator recomputes those fingerprints after Memanto's
OKF loader reads the bundle, proving every allow-listed title, body, tag,
timestamp, provenance field, source reference, and confidence value survived
serialization exactly.

The test suite explicitly plants an email in the source execution and asserts
that it appears nowhere in the generated bundle.

## Import through the shipped Memanto CLI

Preview the exact rows without writing:

```bash
memanto migrate okf examples/migrations/n8n_executions/sample-okf --dry-run
```

Then import into an active agent:

```bash
memanto migrate okf examples/migrations/n8n_executions/sample-okf \
  --agent n8n-operations
```

Finally, prove the memory is portable in both directions:

```bash
memanto memory export --agent n8n-operations --okf --split file \
  --output ./n8n-operations-roundtrip
```

For one guarded live freedom loop, review the secret-free command plan first:

```bash
python -m examples.migrations.n8n_executions.run_live_demo \
  --agent n8n-operations \
  --reuse-agent
```

Then place the Moorcheh key only in the process environment and add
`--execute`. The runner activates or creates the dedicated agent, imports all
three memories through the shipped CLI, retries three real `memanto answer`
questions while indexing settles, requires the expected facts in every live
RAG answer, exports the agent back to OKF under Memanto's guarded data
directory, validates every expected fact in the exported Markdown, and only
then copies the sanitized Q&A and round-trip evidence into this example.

The key is never accepted as a CLI argument, printed, or written to the report.
Existing evidence directories are never overwritten. When `--reuse-agent` is
selected, a live preflight proves the agent is empty before importing; a
populated or ambiguous agent is rejected to prevent duplicate evidence.

## Recorded live proof

The committed proof was captured on 2026-07-30 UTC with the fresh dedicated
agent `n8n-operations-proof`:

| Live stage | Verified result |
| --- | ---: |
| Shipped OKF import | `3 imported · 0 failed` |
| Golden RAG questions | `3/3`, each on the first attempt |
| Shipped OKF export | `3 memories` |
| Exported factual validation | all expected facts present |

See `live-validation.json` for the sanitized full CLI Q&A and
`live-roundtrip-okf/` for the exported OKF bundle. No API key or private
machine path is present in either artifact.

## Safety notes

- Do not commit raw production execution exports.
- Avoid mapping secrets, authorization headers, binary data, or personal data.
- Use a dedicated read-only n8n API key where your deployment supports it.
- Review the generated Markdown before importing it into a long-lived agent.
- This adapter never calls n8n during conversion and never uploads source data.
