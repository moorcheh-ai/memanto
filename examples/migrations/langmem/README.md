# LangMem indexed store to Memanto OKF

Export a LangMem/LangGraph store to portable Markdown, retaining exact source namespace, key, JSON value, and timestamps. The adapter uses Memanto's shipped `OkfExportService`, checks every record through its real OKF loader and mapper, then runs `memanto migrate okf --dry-run`.

The example creates synthetic data through LangMem's real memory management tool across two namespaces, updates one record and deletes another. Local FastEmbed retrieval exercises three paraphrases and an unrelated control. No source LLM, cloud account, or private conversation archive is needed.

## Run

Use Python 3.12 from the repository root:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -e . -r examples/migrations/langmem/requirements.txt
.venv/bin/python examples/migrations/langmem/run.py --output ./langmem-run
```

The first run downloads `BAAI/bge-small-en-v1.5` for local ONNX embeddings. The command above writes `./langmem-run/`. Without `--output`, each invocation selects a new `artifacts/run-<id>/` directory so the committed sample is never overwritten. The committed reference run remains in `artifacts/sample-run/`. Each run contains:

- `langmem_export.json`: actual source-tool records.
- `okf-bundle/`: readable Markdown plus exact encoded source snapshots.
- `run-report.json`: counts, bytes, types, and source retrieval observations.
- `cli-dry-run.txt`: the shipped CLI's import preview.

Use `--output /path/to/new-run` to run again. Existing run directories are rejected. Output is staged and published only after validation and the CLI dry-run succeed.

## Your own store

Call `export_records(store, namespace_prefixes)` from `run.py` against an existing LangGraph store and save the returned JSON. Reads are paginated; overlapping prefixes are deduplicated by exact namespace and key. Pause writes while exporting: offset pagination cannot provide a consistent snapshot of a changing store. Only current records are exported, not deleted records or historical versions.

```sh
.venv/bin/python examples/migrations/langmem/run.py --source-export ./langmem-export.json --output ./migration-run
```

File mode does not generate synthetic data or run unrelated retrieval queries. The JSON shape is `{"memories": [record, ...]}` with an optional matching `count`. Each record requires a nonempty string-array `namespace`, a nonempty string `key`, and an object `value`. Original `created_at` and `updated_at` ISO timestamps may also be supplied. Duplicate identities and non-finite JSON numbers are rejected.

## Mapping and fidelity

| Source | OKF / Memanto |
| --- | --- |
| `value.content` or object value | Human-readable body |
| Namespace + key | SHA-256 of canonical JSON in `langmem://store/...` resource |
| Complete original record | Exact base64 JSON block in the body |
| `created_at`, `updated_at` | Timestamp fields when supplied, also retained in snapshot |
| Untyped memory | `preference` when content contains prefer/likes/requires, otherwise `fact` |

The type rule is a simple heuristic, not semantic inference. Source IDs remain provenance; native Memanto IDs may differ. The body escapes Memanto's entry separator and the adapter's snapshot marker; the encoded snapshot retains the original strings exactly. Metadata is stored in the snapshot rather than relying on the importer's truncated metadata footer.

The adapter refuses records whose body/snapshot exceeds its conservative 8,500-character budget. It decodes every snapshot from the actual mapped payload and compares exact records. This checks local import fidelity; it does not prove remote retention or retrieval.

## Reports and live validation

Source retrieval reports scores and expected phrases. An unrelated query can still return a weak match: no universal threshold or perfect-recall claim is made. File-only imports report source retrieval as not run.

Byte counts measure the serialized source and generated OKF files. Base64 and Markdown generally increase storage. Direct OKF migration has no provider-style savings report; cost and latency savings are unavailable.

A real Moorcheh run is included in `artifacts/cloud-run/`. Four records imported and all four original snapshots were recovered exactly from the cloud re-export. Source top-1 retrieval matched 3/3 positive questions; target top-1 matched 2/3 (the Delhi answer ranked second, tied in score with the first result). All three expected facts appeared in the returned hits. Both systems returned matches for the unrelated control. This is evidence of record conservation, not equivalent retrieval quality.

The recorded import succeeded before an export-path error; validation resumed without importing duplicates. `original-cli-import.txt` and `live-report.json` explain that sequence. Source JSON is 1,086 bytes, local OKF is 4,856 bytes, and the cloud re-export including session context is 10,578 bytes. No savings are claimed.

The [87-second recorded demonstration](https://youtu.be/drDLkrKyhms) shows a fresh source run, a new empty source store, the actual cloud import, target recall, readable cloud-exported Markdown, and a real cloud answer identifying Delhi and masala tea. `artifacts/recorded-run/` contains the matching CLI logs, source export, recall/conservation report, and answer. Its cloud bundle is 10,598 bytes including session context. The video runs import separately, then uses `--resume-after-import` for validation to avoid duplicate writes. It is a screen recording of a local browser console streaming the real commands and their results.

## Optional live validation

After the local run, prepare a uniquely named demo agent and activate that exact
agent in the Memanto CLI. The runner checks the active agent/session before importing. Existing CLI configuration requires the explicit `--allow-shared-config` flag; check the account and target before using it.
Keep `MOORCHEH_API_KEY` in the process environment; it is never printed or
written to the report.

```sh
export MOORCHEH_API_KEY='...'
.venv/bin/python -m memanto agent create <unique-demo-agent-id>
LIVE_DIR="examples/migrations/langmem/artifacts/live-$(date +%Y%m%d-%H%M%S)"
.venv/bin/python examples/migrations/langmem/live_workflow.py \
  --bundle ./langmem-run/okf-bundle \
  --source-export ./langmem-run/langmem_export.json \
  --source-report ./langmem-run/run-report.json \
  --agent <unique-demo-agent-id> \
  --allow-shared-config \
  --output "$LIVE_DIR"
```

Use `--allow-shared-config` only after confirming that the existing CLI config
contains the dedicated demo account and the same target agent; omit it to keep
the collision guard active.

This invokes `memanto migrate okf` for the import and `memanto memory export
--okf` for the re-export, and uses the SDK for the source report's recall questions. The
resulting `live-report.json`, `cli-import.txt`, and `cli-export.txt` record each top score, returned hit id/content,
recall timing, import/export timing, source/target bytes, and exact snapshot
missing/unexpected/changed identities. It reports cost and latency savings as
unavailable; no savings are inferred from byte or timing measurements. The
runner does not activate or delete agents and refuses an existing output directory. Import adds memories to the explicitly selected agent. Exports are first written to a unique directory under `~/.memanto/exports` as the shipped CLI requires, then copied to the run directory. Those export files remain available locally. Use `--resume-after-import` only after confirming an earlier import succeeded; the report marks import as skipped and does not invent its timing.

## Checks

```sh
.venv/bin/pytest examples/migrations/langmem/tests -q
.venv/bin/ruff check examples/migrations/langmem
.venv/bin/ruff format --check examples/migrations/langmem
```

Tests cover 1,001-record pagination, overlapping scopes, namespace collisions, Unicode/delimiters, exact conservation, malformed/oversized records, deletion, output preservation, and actual file-mode CLI import. Install `pytest`, `pytest-asyncio`, `pytest-timeout`, and `ruff` as development tools.
