# Codex CLI sessions to portable OKF

This Path B adapter liberates conversational memory from a real Codex CLI
rollout (`rollout-*.jsonl`) into a human-readable Open Knowledge Format bundle.
It feeds Memanto's shipped `migrate okf` path; it does not reimplement Memanto's
loader or migration engine.

The important twist is privacy. Codex rollouts can contain tool output,
reasoning, credentials, paths, and pasted account data. This adapter exports
only user/assistant text, excludes internal context and images, applies
deterministic redaction, and fails closed if the published text still resembles
a credential, email address, JWT, or long base58 account identifier.

## What the included real-data artifact proves

`sample_okf/` was generated from a lived-in, multi-day Codex session used for a
real software delivery workflow—not handwritten fixture data. The private raw
rollout is not published because doing so would defeat the privacy story.
Instead, the bundle carries cryptographic provenance:

- the manifest records the SHA-256 digest and byte size of the frozen raw
  rollout without recording its local path;
- every OKF document carries the SHA-256 digest of its canonical source
  envelope and its privacy-redacted body;
- the validator re-reads the private source, proves every selected source
  record exists, verifies exact body parity, and runs the privacy gate;
- `artifacts/roundtrip_report.json` records 100% source-to-OKF coverage, exact
  content-hash parity, and zero privacy findings;
- Memanto's shipped loader maps all 14 sample OKF nodes and skips zero.

The raw source remains genuinely verifiable during review or a live demo while
the public artifact remains safe to inspect and fork.

## One-command reproducibility

From the repository root, install the project and point the demo at any real
Codex rollout:

```bash
uv sync --group dev
uv run python examples/migrations/codex_cli_sessions/run_demo.py \
  ~/.codex/sessions/2026/08/01/rollout-....jsonl \
  --output ./codex-okf-demo \
  --include "architecture|decision|preference" \
  --max-records 25 \
  --redact-literal "Your Name"
```

On Windows PowerShell, quote the rollout path and keep the command on one line:

```powershell
uv run python examples/migrations/codex_cli_sessions/run_demo.py "C:\Users\you\.codex\sessions\2026\08\01\rollout-....jsonl" --output .\codex-okf-demo --include "architecture|decision|preference" --max-records 25 --redact-literal "Your Name"
```

The command performs the full non-live proof:

1. parses a real rollout;
2. selects and privacy-redacts conversation memories;
3. writes an OKF bundle and provenance manifest;
4. validates source coverage and exact content parity;
5. loads and maps the bundle through Memanto's shipped OKF code;
6. writes `roundtrip_report.json` and `memanto_dry_run_report.json`.

For the actual CLI dry-run:

```bash
memanto migrate okf ./codex-okf-demo --dry-run
```

No Moorcheh API key is required for either dry-run. A live import uses the
normal Memanto flow:

```bash
memanto migrate okf ./codex-okf-demo --agent your-agent
memanto memory export --agent your-agent --okf
```

## Source-to-OKF mapping

| Codex rollout concept | Selection rule | OKF representation | Memanto behavior |
| --- | --- | --- | --- |
| `session_meta` | Used only to bind following messages to a session | Hashed `resource: codex://session/...` | Preserved as pseudonymous source reference |
| `response_item/message`, role `user` | Text blocks only; internal context excluded | One OKF document tagged `user` | Auto-classified on import |
| `response_item/message`, role `assistant` | Public `output_text` only | One OKF document tagged `assistant` | Auto-classified on import |
| Message timestamp | Preserved | `timestamp` | Preserved as creation time |
| Canonical source envelope | SHA-256 only; raw text stays private | `source_record_sha256` extension | Preserved in supporting data |
| Redacted message body | Exact UTF-8 text | Markdown body + `content_sha256` | Imported as memory content |
| Tool calls and tool outputs | Always excluded | None | Never ingested |
| Reasoning records | Always excluded | None | Never ingested |
| Developer instructions | Always excluded | None | Never ingested |
| Images and attachments | Always excluded | None | Never ingested |

Unknown frontmatter fields are intentionally used for provenance. Memanto's OKF
loader preserves them in the imported memory's supporting-data footer, so the
round trip is lossless without forcing Codex concepts into Memanto's schema.

## Fidelity and validation

The source-record digest is calculated from canonical JSON containing the
session id, JSONL line number, timestamp, role, and original text. Validation
recomputes those digests from the raw rollout and checks that the selected set
matches the OKF and manifest sets exactly. It then hashes each redacted Markdown
body and compares it with the recorded digest. A modified, missing, or invented
entry fails validation.

Run the focused checks:

```bash
uv run pytest examples/migrations/codex_cli_sessions/tests -q
uv run ruff check examples/migrations/codex_cli_sessions
uv run ruff format --check examples/migrations/codex_cli_sessions
```

## Honest savings report

Codex rollouts and OKF bundles are local files. There is no provider API call,
token bill, or retrieval-latency baseline to compare, so this showcase does not
invent one. The generated manifest reports only measurable values: raw rollout
bytes, selected source-text bytes, published redacted-text bytes, record counts,
and redaction counts. Both source and migration API-call counts are zero.

## Privacy model and limitations

- `--include` and `--exclude` run before redaction; do not publish those private
  selector values if they identify a person or project.
- `--redact-literal` values are applied case-insensitively and are never stored
  in the manifest.
- Automated redaction is defense in depth, not a substitute for reviewing a
  public artifact. Run the validator and inspect the final Markdown before
  publishing it.
- The adapter preserves conversation memory, not hidden chain-of-thought. That
  exclusion is deliberate and permanent.
- A source digest proves which frozen file was used; a reviewer can reproduce
  the proof when given that file privately without requiring it in git.
