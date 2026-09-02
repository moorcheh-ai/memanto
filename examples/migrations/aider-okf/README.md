# Aider to Memanto to OKF

This showcase releases coding-agent context from Aider's native
`.aider.chat.history.md` into portable OKF 0.2 Markdown. It uses Aider's own
role markers instead of inventing a JSON schema, preserves every included
record byte-for-byte behind a SHA-256 receipt, and feeds the shipped
`memanto migrate okf` command.

The checked-in source is genuine output from four Aider 0.86.2 runs backed by
the local `qwen2.5-coder:3b` Ollama model. `generate_source.py` contains the
exact prompts and command. Its only post-processing replaces machine-specific
absolute paths with `<MEMANTO_REPOSITORY>`; conversation and tool content are
otherwise unchanged.

## Mapping

| Aider concept | OKF field | Memanto field |
| --- | --- | --- |
| User input (`####`) | `type: instruction`, Markdown body | `instruction.content` |
| Assistant output | `type: context`, Markdown body | `context.content` |
| Tool output (`>`) | `type: context`, Markdown body | `context.content` |
| Session start | `timestamp`, `x_memanto.created_at` | `created_at` |
| Role and ordinal | `x_aider.role`, `x_aider.ordinal` | lossless supporting data |
| Source/content hashes | `x_aider.*_sha256` | lossless supporting data |

Unknown `x_aider` fields survive Memanto's OKF loader in its supporting-data
footer, so another consumer can audit or reconstruct the original messages.

## Reproduce in under 15 minutes

Requirements: Python 3.10-3.12 and `uv`. Only source regeneration additionally
needs Ollama with `qwen2.5-coder:3b`.

```bash
uv sync
uv run --python 3.12 examples/migrations/aider-okf/aider_okf.py \
  examples/migrations/aider-okf/data/aider.chat.history.md \
  /tmp/aider-okf

uv run memanto migrate okf /tmp/aider-okf --dry-run

uv run --python 3.12 examples/migrations/aider-okf/validate.py \
  examples/migrations/aider-okf/data/aider.chat.history.md \
  /tmp/aider-okf
```

The checked-in run reports 16 source records, 16 valid OKF nodes, 16 mapped
Memanto memories, zero skipped records, 16/16 exact content hashes, and 4/4
golden recall parity. See `receipt.yaml` for the machine-readable evidence.

To regenerate the genuine source rather than reuse the public sample:

```bash
ollama pull qwen2.5-coder:3b
uv run --python 3.12 examples/migrations/aider-okf/generate_source.py
```

## Live freedom loop

After selecting a Memanto agent and configuring a Moorcheh API key, replace
the dry run with the write and export commands:

```bash
memanto migrate okf /tmp/aider-okf --agent "$AGENT_ID"
memanto memory export --okf --agent "$AGENT_ID"
```

The adapter deliberately refuses to overwrite an existing output directory
and fails privacy preflight without echoing any matched secret. Review a source
archive before publishing it; Aider histories can contain prompts, model
answers, command output, and paths.

## Verification

```bash
uv run pytest examples/migrations/aider-okf/tests -q
uv run ruff check examples/migrations/aider-okf
uv run ruff format --check examples/migrations/aider-okf
uv run mypy examples/migrations/aider-okf/aider_okf.py \
  examples/migrations/aider-okf/generate_source.py \
  examples/migrations/aider-okf/validate.py
```
