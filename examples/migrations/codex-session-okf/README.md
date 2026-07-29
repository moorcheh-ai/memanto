# Codex session → privacy-filtered OKF

This adapter turns a genuine Codex CLI rollout (`rollout-*.jsonl`) into a
portable, human-readable OKF bundle. It demonstrates a new migration path for
agent conversations while keeping Codex internals and operator identity out of
the export.

## Why this source matters

Codex sessions contain useful decisions, preferences, and outcomes, but the
rollout format also mixes those messages with system/developer instructions,
reasoning, tool calls, and transport metadata. Copying the JSONL wholesale into
a memory system would leak irrelevant privileged context.

This adapter applies a deny-by-default boundary:

- includes only `response_item` records whose payload is a `message`;
- allows only `user` and `assistant` roles;
- excludes reasoning, tools, function arguments/results, system instructions,
  developer instructions, and world/turn state;
- removes Lark/Bridge transport blocks;
- redacts email addresses, phone numbers, Bridge IDs, common token prefixes,
  and sensitive URL query values;
- emits a source fingerprint rather than the source path or session ID.

Always review the generated Markdown before importing or publishing it.

## Mapping

| Codex concept | OKF / Memanto field |
| --- | --- |
| User or assistant message | One OKF `conversation` node |
| Conversation node | Memanto `context` memory via `x_memanto.type` |
| Record timestamp | `timestamp` |
| Message role | `x_memanto.role` and `role-*` tag |
| Rollout file | Truncated SHA-256 source fingerprint |
| JSONL line | `x_memanto.source_line` |
| Message text | Markdown body |
| Privacy pass | `x_memanto.privacy_filtered: true` |

Reasoning and tool records intentionally have no mapping.

## Human-reviewed product boundary

The contributor reviewed whether sanitized tool-call summaries should be
included and chose to keep the export strict: only user and assistant text is
portable memory. Tool execution details are not treated as long-term memory,
and including them would increase privacy risk. The decision is recorded in
`HUMAN_REVIEW.md`.

## Run

From this directory:

```bash
python3 convert.py /path/to/rollout.jsonl ./my-codex-okf
python3 -m pytest -q tests
python3 validate.py sample/source-session.jsonl ./my-codex-okf \
  sample/golden_qa.json
memanto migrate okf ./my-codex-okf --dry-run
```

To export only messages relevant to a showcase:

```bash
python3 convert.py /path/to/rollout.jsonl ./my-codex-okf \
  --include 'workspace|date|migration' \
  --limit 20
```

The bundled `run_demo.sh` uses the committed privacy-safe sample:

```bash
./run_demo.sh
```

## Reproducible validation

The test suite verifies:

1. only user and assistant message records are exported;
2. developer instructions and tool payloads never enter the bundle;
3. Bridge wrappers are removed and their user text is decoded;
4. common identifiers are redacted;
5. filtering and limiting are deterministic.

`validate.py` adds a deterministic golden Q&A gate. For every question it
checks that the expected facts are present in both the genuine source archive
and the portable OKF output. The committed showcase reports 3/3 source recall,
3/3 OKF recall, and exact parity for all questions.

The sample archive is derived from a real Codex session. It contains only
benign messages selected for the public demo and has been passed through the
same privacy filter. The generated OKF is committed so reviewers can inspect
the exact artifact without running Codex.

## Full freedom loop

```text
Codex rollout JSONL
        ↓ convert.py
privacy-filtered OKF (readable Markdown)
        ↓ memanto migrate okf
Memanto memory
        ↓ memanto memory export --okf
portable OKF again
```

Live Memanto import/export requires a Moorcheh API key. The conversion and all
privacy tests run fully offline.

The committed [`LIVE_VALIDATION.md`](LIVE_VALIDATION.md) records a cloud-backed
import, retrieval, and OKF re-export run without including credentials or cloud
record identifiers.

The OKF migration command does not generate the provider-migration savings
report because OKF is already a local portable bundle. Do not claim token,
latency, or storage savings from its dry run; report measured source/output
sizes and live timings separately when recording a showcase.
