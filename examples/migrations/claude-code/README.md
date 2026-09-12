# Claude Code local memory → portable OKF

Claude Code keeps durable project knowledge in local Markdown, JSONL history,
transcripts, and todo state. This example turns that user-owned state into a
human-readable Open Knowledge Format (OKF) bundle that Memanto's shipped
`migrate okf` command can preview or import.

The committed fixture is a privacy-redacted extract from an actual, lived-in
Claude Code project. It is not a synthetic conversation export. See
[`sample_data/PROVENANCE.md`](sample_data/PROVENANCE.md) for the source and
redaction record.

## One-command sample

From the repository root:

```bash
./examples/migrations/claude-code/run_sample.sh
```

The command:

1. reads the real-format Claude Code sample;
2. writes it through Memanto's existing `OkfExportService`;
3. scores five golden questions before and after conversion; and
4. runs `memanto migrate okf --dry-run` against the result.

Expected evidence:

| Measure | Result |
| --- | ---: |
| Source records read | 5 |
| Mapped OKF memories | 3 |
| Skipped records | 0 |
| Memanto dry-run mappings | 3 |
| Memanto dry-run skips | 0 |
| Source recall | 5/5 (100%) |
| OKF recall | 5/5 (100%) |
| Recall parity delta | 0.0 points |

The generated, reviewable evidence is committed under
[`sample_output/`](sample_output/).

- [`DRY_RUN.md`](sample_output/DRY_RUN.md) records the shipped importer's
  zero-skip result without machine-local paths.
- [`SAVINGS_REPORT.md`](sample_output/SAVINGS_REPORT.md) explains why an OKF
  source has no provider savings report and lists the evidence used instead.

## Migrate your own Claude Code project

Claude Code's default local state directory is `~/.claude`. Pass the original
project path exactly as Claude Code recorded it:

```bash
uv run python examples/migrations/claude-code/claude_code_to_okf.py \
  --project /absolute/path/to/your/project \
  --output ./claude-code-okf
```

The adapter discovers the matching `~/.claude/projects/<slug>` directory. If
your Claude Code version uses an ambiguous or legacy slug, pass it explicitly:

```bash
uv run python examples/migrations/claude-code/claude_code_to_okf.py \
  --claude-home ~/.claude \
  --project /absolute/path/to/your/project \
  --project-data ~/.claude/projects/-absolute-path-to-your-project \
  --output ./claude-code-okf
```

Preview the portable bundle through Memanto's shipped importer:

```bash
uv run memanto migrate okf ./claude-code-okf --dry-run
```

After configuring a Memanto agent and Moorcheh API key, import and export the
owned memory again:

```bash
uv run memanto migrate okf ./claude-code-okf --agent my-agent
uv run memanto memory export --agent my-agent --okf --output ./owned-again-okf
```

To run the sample import and live semantic-recall check in one command, set an
existing agent explicitly:

```bash
MEMANTO_LIVE_AGENT=my-agent \
  ./examples/migrations/claude-code/run_sample.sh .local-output
```

The environment variable is required so the default sample remains read-only:
without it, the script stops after Memanto's `--dry-run`.

The OKF importer intentionally has no provider savings report; this is stated
by `memanto migrate okf --help`. This showcase reports conversion counts,
mapping fidelity, redactions, and recall parity instead of inventing token,
latency, or storage savings.

## Source → Memanto → OKF mapping

| Claude Code source | Selection rule | Memanto type | OKF representation |
| --- | --- | --- | --- |
| `memory/*.md`, `type: feedback` | Non-empty document; `MEMORY.md` index excluded | `instruction` | Title/body, source tag, redacted source path |
| `memory/*.md`, `type: user` | Non-empty document | `preference` | Title/body, source tag, redacted source path |
| `memory/*.md`, `type: project` | Non-empty document | `fact` | Title/body, source tag, redacted source path |
| `memory/*.md`, `type: reference` | Non-empty document | `artifact` | Title/body, source tag, redacted source path |
| Other `memory/*.md` | Non-empty document | `context` | Title/body plus original Claude memory type |
| `history.jsonl` | User prompts for the selected project, grouped by session | `context` | Ordered prompt sections and hashed session fingerprint |
| Project transcript JSONL | User/assistant natural-language text only | `context` | Ordered turns; tool payloads excluded |
| `todos/*.json`, pending | Session observed for the selected project | `commitment` | Todo text, status tag, hashed session fingerprint |
| `todos/*.json`, completed | Session observed for the selected project | `event` | Todo text, status tag, hashed session fingerprint |

Every output entry receives:

- a stable, non-identifying `resource`/source reference;
- `provenance: imported` and `source: claude-code`;
- Claude source tags and useful bounded metadata;
- the original timestamp where the source supplies one; and
- a valid OKF type handled by Memanto's existing loader and mapper.

## Privacy boundary

The adapter reads only durable, user-owned text. It excludes tool payloads,
telemetry, attachments, pasted-content blobs, file-history snapshots, shell
environment captures, and subagent transcripts by default.

Before writing any selected text it redacts:

- the project and home paths;
- common API-key, bearer-token, GitHub-token, private-key, and credential
  assignment shapes; and
- email addresses.

Use `--no-history`, `--no-transcripts`, or `--no-todos` to narrow the input
further. `--include-subagents` is an explicit opt-in. An existing output
directory is never replaced unless `--force` is passed.

## Validation method

[`validation/golden_qa.json`](validation/golden_qa.json) contains five
questions grounded in the source project. The validator builds one corpus from
the selected Claude Code records and a second from the OKF loader's importable
fields. A question passes only when every semantic term group has at least one
accepted term. Equal before/after scores prove deterministic recall parity for
the committed sample without pretending that substring matching is an LLM
quality judgment.

## Files

```text
claude-code/
├── claude_code_to_okf.py       # adapter and OKF writer
├── run_sample.sh               # one-command reproducible pipeline
├── sample_data/                # privacy-redacted real Claude Code state
├── sample_output/              # committed OKF and validation evidence
└── validation/
    ├── golden_qa.json
    ├── validate_live_recall.py
    └── validate_recall.py
```
