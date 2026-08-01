# ChatGPT Export → Open Knowledge Format (OKF)

Portable, privacy-aware migration tooling for converting an official ChatGPT
data export into a human-readable [Open Knowledge Format][okf] bundle. It is
designed as a contribution for Memanto's memory-portability showcase: the
converter creates a vendor-neutral OKF bundle, rather than coupling the
archive to a new database schema.

[okf]: https://docs.memanto.ai/integrations/okf

## What it preserves

For every assistant response in an exported conversation, the converter writes
one `event` document. It preserves the response, its preceding user context,
the source conversation title, timestamps, and stable source identifiers. A
`manifest.json` contains SHA-256 checksums for both the source-derived record
and the generated markdown document. This makes a migration auditable without
putting private data in a third-party service.

The source export is never uploaded by this project. By default the converter
redacts common secrets (API tokens), email addresses, and crypto addresses
from generated artifacts. Use `--no-redact` only after deciding that the
output may safely be committed or shared.

## Run it

Export your ChatGPT data through ChatGPT's data-export flow and unzip it
locally. Then run one command:

```powershell
python run_demo.py --export "C:\path\to\ChatGPT-export\conversations.json" --out artifacts
```

`--export` can point at `conversations.json`, another explicit JSON export
fixture, or the root of an unzipped official export. The command converts the archive, validates the bundle, and writes a
reproducibility report to `artifacts/report.json`.

For a safe smoke test, use the intentionally synthetic fixture:

```powershell
python run_demo.py --export fixtures/sample_conversations.json --out artifacts-sample
```

The fixture is only a schema test. It is **not** evidence for a bounty
submission. A real submission must run the same command against a genuine
export and include the resulting reports with any sensitive content removed.

## Optional Memanto import preview

After installing Memanto, preview its import without writing anything:

```powershell
memanto migrate okf artifacts/okf --dry-run
```

When a target agent is configured, import it with `memanto migrate okf
artifacts/okf`, then export it again with `memanto memory export --okf`. This
is the final round-trip that should be recorded in a public demo. Memanto's
OKF importer preserves unmapped fields in a supporting-data footer, so this
adapter deliberately keeps source identifiers and the redaction state in the
frontmatter.

## Output layout

```text
artifacts/
├── okf/
│   ├── index.md
│   ├── manifest.json
│   └── memories/event/*.md
└── report.json
```

The output adheres to the minimum OKF rule: each node is Markdown with YAML
frontmatter and a `type`. The document body stays readable in any editor or
Git viewer.

## Verification

```powershell
python -m unittest discover -s tests -v
python validate_okf.py artifacts/okf
```

The validator checks bundle structure, IDs, required frontmatter, manifest
coverage, and SHA-256 integrity. It does not claim semantic or retrieval
parity; that evidence must come from a real Memanto import/export run.

## Demo checklist

See [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for a short, honest screen-recording
script. In particular, do not show raw personal conversations, API keys,
wallet addresses, or any account details in the recording.

## License

MIT. This standalone contribution is intended to be copied into
`examples/migrations/chatgpt-export-okf/` in the upstream repository.
