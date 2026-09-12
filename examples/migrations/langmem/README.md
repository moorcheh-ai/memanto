# LangMem indexed store to Memanto OKF

Export a LangMem/LangGraph store to portable Markdown, retaining exact source namespace, key, JSON value, and timestamps. The adapter uses Memanto's shipped `OkfExportService`, checks every record through its real OKF loader and mapper, then runs `memanto migrate okf --dry-run`.

The example creates synthetic data through LangMem's real memory management tool across two namespaces, updates one record and deletes another. Local FastEmbed retrieval exercises three paraphrases and an unrelated control. No source LLM, cloud account, or private conversation archive is needed.

## Run

Use Python 3.12 from the repository root:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -e . -r examples/migrations/langmem/requirements.txt
.venv/bin/python examples/migrations/langmem/run.py
```

The first run downloads `BAAI/bge-small-en-v1.5` for local ONNX embeddings. Output goes into `examples/migrations/langmem/artifacts/sample-run/`:

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

## Reports and remaining live validation

Source retrieval reports scores and expected phrases. An unrelated query can still return a weak match: no universal threshold or perfect-recall claim is made. File-only imports report source retrieval as not run.

Byte counts measure the serialized source and generated OKF files. Base64 and Markdown generally increase storage. Direct OKF migration has no provider-style savings report; cost and latency savings are unavailable.

Cloud import, target recall, re-export, live demo video, and bounty claim remain pending. After configuring a dedicated Memanto agent, the remaining workflow starts with:

```sh
memanto migrate okf ./migration-run/okf-bundle --agent <demo-agent>
memanto memory export --okf
```

Remote validation must decode source snapshots again and compare source and target retrieval before describing the full migration as lossless or equivalent.

## Checks

```sh
.venv/bin/pytest examples/migrations/langmem/tests -q
.venv/bin/ruff check examples/migrations/langmem
.venv/bin/ruff format --check examples/migrations/langmem
```

Tests cover 1,001-record pagination, overlapping scopes, namespace collisions, Unicode/delimiters, exact conservation, malformed/oversized records, deletion, output preservation, and actual file-mode CLI import. Install `pytest`, `pytest-asyncio`, `pytest-timeout`, and `ruff` as development tools.
