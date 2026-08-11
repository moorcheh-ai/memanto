# PydanticAI message history → Memanto → portable OKF

This Path B showcase adds a migration route absent from Memanto and from the
other active bounty submissions: persisted
[PydanticAI message history](https://pydantic.dev/docs/ai/core-concepts/message-history/)
to a human-readable Open Knowledge Format bundle consumed by Memanto's shipped
`memanto migrate okf` command.

```text
PydanticAI Agent runs
        │  RunResult.all_messages_json()
        ▼
ModelMessage JSON ── adapter.py ──► OKF Markdown + canonical sidecars
                                      │
                                      ├── memanto migrate okf --dry-run
                                      ├── reconstruct.py (hash-verified)
                                      └── validate.py (golden recall parity)
```

## Verified public sample

| Evidence | Result |
|---|---:|
| Genuine PydanticAI turns | 8 |
| PydanticAI messages | 20 |
| Tool dispatches | 2 |
| OKF memory nodes | 20 |
| Memanto mapped / skipped | 20 / 0 |
| Canonical reconstruction | 20 / 20, SHA-256 match |
| Golden recall parity | 6/6 source → 6/6 OKF |
| Privacy findings | 0 |

The sample is a genuine run of `pydantic-ai-slim==2.27.1`: PydanticAI creates
the message objects, timestamps, usage, run IDs, conversation IDs, tool calls,
tool returns, and serialized archive. The generator also validates and
byte-round-trips that archive with PydanticAI's official
`ModelMessagesTypeAdapter`. A deterministic `FunctionModel` supplies the public
demo responses so reproduction requires no model API key or spend. That
distinction is recorded in `sample/evidence/source-run.json`; no live LLM
generation is claimed.

The messages capture decisions and corrections from building this migration
adapter itself, rather than hand-authored JSON pretending to be a provider
export. `generate_source.py` is the exact source-population script.

## Reproduce in under 15 minutes

From this folder, using Python 3.10+:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e ../../..

python run_demo.py --work-dir ./demo-output
```

Use `--force` only when intentionally replacing a prior adapter-generated demo
under that work directory.

The command fails on the first error and performs the complete credential-free
loop:

1. runs the PydanticAI Agent across eight turns;
2. serializes its real `ModelMessage` history;
3. scans the source for secrets and PII;
4. creates the OKF bundle;
5. runs Memanto's shipped `migrate okf --dry-run` path;
6. reconstructs and hash-checks the canonical source;
7. scores the same golden questions against source and OKF.

Use `--transcript path/to/file.txt` to retain the console transcript. Without
`--work-dir`, all generated artifacts use an automatically removed temporary
directory.

## Migrate your own PydanticAI history

Persist messages using the official API:

```python
history_json = result.all_messages_json()
Path("history.json").write_bytes(history_json)
```

Then convert and preview:

```bash
python adapter.py history.json --output ./my-okf
memanto migrate okf ./my-okf --dry-run
```

After reviewing the Markdown and mapped preview, import into a real agent:

```bash
memanto migrate okf ./my-okf --agent YOUR_AGENT_ID
memanto memory export --okf --agent YOUR_AGENT_ID
```

The last two commands require your own configured Moorcheh/Memanto account.
This repository contains no credentials and does not claim those live steps
were run unless a corresponding real report is present.

## Privacy before portability

OKF is deliberately plaintext. The adapter recursively scans all source
strings and refuses to write when it sees likely secrets or PII. Reports record
only category, JSON path, severity, and a hash prefix—never the matched value.

```bash
# Recommended: sanitize the archive, then run normally.
python adapter.py sanitized.json --output ./okf

# Explicitly redact known patterns; report becomes lossless=false.
python adapter.py history.json --output ./okf --redact

# Retain findings only after accepting the plaintext risk.
python adapter.py history.json --output ./okf --allow-sensitive
```

See [MAPPING.md](MAPPING.md) for the source-to-OKF table, fidelity contract,
and privacy model.

## Why one message per memory?

Flattening an agent history destroys causality. A `ToolReturnPart` may share a
request with another user part, and future PydanticAI versions can add fields or
part kinds. This adapter preserves every message boundary and stores the full
canonical source object in a hashed sidecar. The Markdown body is optimized for
humans; the sidecar is optimized for exact ownership and future migration.

Unambiguous system-only, tool-only, and retry messages map to Memanto
`instruction`, `artifact`, and `error` types. User and assistant prose remain
`auto` so the adapter never pretends it can distinguish a fact, preference,
decision, or correction from syntax alone.

## Evidence and limitations

- `sample/okf/` is the complete, human-inspectable bundle.
- `sample/evidence/freedom-loop.txt` is the sanitized transcript from every
  validation stage; `memanto-dry-run.txt` and `memanto-mapped-preview.json`
  preserve the shipped CLI's exact dry-run evidence.
- `sample/evidence/validation-report.json` contains mapping, privacy,
  reconstruction, measured-byte, and recall evidence.
- `sample/evidence/source-run.json` identifies the exact framework version and
  deterministic model caveat.
- `sample/golden_qa.json` contains the six versioned questions.

Measured context-byte reduction is reported; token, price, storage-service, and
network-latency savings are not invented. A live Moorcheh import, public demo
video, and public social metrics are owner-run bounty evidence and must be added
before claiming the bounty. Follow [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for the
recording.

For a credentialed import, export-back, and recall evidence checklist, follow
[OWNER_VALIDATION.md](OWNER_VALIDATION.md). It deliberately requires the owner
to run and inspect every external operation.

## Test

From the repository root:

```bash
pytest tests/test_pydanticai_history_migration.py -q
ruff check examples/migrations/pydanticai-history-okf tests/test_pydanticai_history_migration.py
ruff format --check examples/migrations/pydanticai-history-okf tests/test_pydanticai_history_migration.py
```
