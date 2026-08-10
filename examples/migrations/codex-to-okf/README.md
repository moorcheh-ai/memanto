# Codex rollout → portable OKF memory

This example turns a genuine OpenAI Codex CLI/Desktop rollout (`.jsonl`) into
a human-readable [Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf)
bundle that Memanto can import. It closes a portability gap the other migration
examples do not address: agent runs often contain valuable goals, constraints,
decisions, and observations, but their raw logs also contain private runtime
state that should never become memory.

The adapter therefore starts with a privacy allow-list, not a data dump.

## What makes this migration different

- **Genuine source data.** `sample_data/codex-rollout-sanitized.jsonl` is a
  privacy-sanitized excerpt generated from a real Codex Desktop task. Its
  `source_sha256` preserves verifiable lineage to the private raw rollout.
- **Safe by default.** Only visible user and assistant messages are eligible.
  Developer instructions, encrypted reasoning, tool calls, tool outputs,
  world state, turn context, and compaction payloads are excluded.
- **Pre-export redaction.** Common API keys, bearer tokens, email addresses,
  and local Windows/POSIX home paths are redacted before classification.
- **Semantic mapping.** User goals and constraints become `goal` and
  `instruction` memories; visible research outcomes become `decision` or
  `observation` memories instead of an opaque transcript blob.
- **Auditable output.** The migration report records source and bundle hashes,
  every excluded record category, redaction counts, type counts, and token
  estimates.
- **Two independent parity checks.** Four golden questions verify that the
  portable bundle still answers the task's core questions with the expected
  memory type. A second check runs it through Memanto's shipped OKF loader,
  mapper, and exporter and proves that all resources, types, titles, and content
  survive the round trip.

## Source → OKF mapping

| Codex source | OKF / Memanto field | Policy |
|---|---|---|
| `session_meta.session_id` | `resource` namespace | Sanitized in the public fixture |
| message `timestamp` | `timestamp` | Normalized to UTC |
| message `role` | `tags: role:*` | User and assistant only |
| user goal sentence | `type: goal` | Confidence `1.0` |
| user prohibition/constraint | `type: instruction` | Confidence `1.0` |
| visible assistant rejection/choice | `type: decision` | Confidence `0.9` |
| visible assistant discovery/status | `type: observation` | Confidence `0.85` |
| other visible content | `fact` or `artifact` | Preserved, lower confidence |
| message ID | `x_memanto.source_ref` | Stable lineage without raw tool data |
| developer/reasoning/tool/runtime records | — | Never exported by default |

## Run the complete reproducible demo

Python 3.10+ is required.

```bash
cd examples/migrations/codex-to-okf
python -m pip install -r requirements.txt
./run.sh
```

On Windows PowerShell:

```powershell
cd examples/migrations/codex-to-okf
python -m pip install -r requirements.txt
.\run.ps1
```

The single command:

1. converts the genuine sanitized rollout;
2. writes a browsable OKF bundle under `sample_output/okf-bundle/`;
3. writes JSON and Markdown migration reports;
4. runs structural validation and the four-question recall-parity suite;
5. maps and re-exports the bundle with Memanto's official implementation;
6. verifies 16/16 resource, type, title, and content parity; and
7. runs Memanto's shipped OKF dry-run and verifies 16 mapped, 0 skipped.

Expected result:

```text
4/4 golden questions passed
recall_parity_percent: 100.0
portability parity: 16/16 (100.0%)
Memanto dry run: 16 mapped, 0 skipped
```

## Use your own Codex rollout

Codex rollout files are commonly stored beneath the Codex data directory in a
date hierarchy. Pass an explicit path so the script never scans your machine:

```bash
python codex_to_okf.py /path/to/rollout.jsonl ./my-okf-bundle \
  --title "My portable Codex memory"
python validate_roundtrip.py ./my-okf-bundle \
  --golden ./golden_qa.json
```

To export only user messages:

```bash
python codex_to_okf.py /path/to/rollout.jsonl ./my-okf-bundle \
  --no-include-assistant
```

The adapter never auto-discovers files, follows links, uploads data, or calls a
model/API. Review the generated Markdown before importing it.

## Import into Memanto and export again

First inspect the mapped payload without writing anything:

```bash
memanto migrate okf ./sample_output/okf-bundle --dry-run
```

Then import into a configured agent and export the memories back to portable
OKF:

```bash
memanto migrate okf ./sample_output/okf-bundle --agent codex-migration-demo
memanto memory export --okf --agent codex-migration-demo
```

That is the complete freedom loop:

```text
Codex rollout -> privacy boundary -> typed OKF -> Memanto -> OKF again
```

The reproducible offline gate exercises that loop through the same loader,
mapper, and exporter used by Memanto without claiming a cloud import:

```bash
python validate_portability.py ./sample_output/okf-bundle \
  ./sample_output/reexported-okf \
  --report ./sample_output/portability-parity.json --replace
```

The checked-in report records 16/16 resources, types, titles, and bodies
preserved. A configured Moorcheh account is still required for the live import
and semantic-recall recording described above.

## Render the demo video

The optional renderer executes the converter, validator, and Memanto dry run
again before recording their privacy-sanitized output:

```bash
python -m pip install -r requirements-demo.txt
python make_demo_video.py ./codex-okf-demo.mp4
```

The checked-in [`demo.m4v`](./demo.m4v) is the reproducible 80-second render
used for challenge review. Re-run the command above to regenerate it.

## Recreate the publishable fixture

`make_sanitized_fixture.py` is the exact script used to derive the checked-in
sample from a genuine rollout:

```bash
python make_sanitized_fixture.py /private/path/rollout.jsonl \
  ./sample_data/codex-rollout-sanitized.jsonl
```

It replaces session/message IDs, runs the same redaction pass, omits private
record classes, and embeds only the raw source SHA-256—not the raw file.

## Privacy threat model

Raw agent logs are not ordinary chat exports. They may include privileged
instructions, hidden reasoning envelopes, command arguments, command outputs,
environment values, and absolute paths. This example treats every record as
private unless its type, payload type, role, and content type are explicitly
allowed.

The redactor is defense in depth, not a guarantee. A human review remains
mandatory before publishing an OKF bundle generated from personal data.

## Evidence included

- `sample_data/codex-rollout-sanitized.jsonl`: genuine sanitized source
- `sample_output/okf-bundle/`: inspectable portable memories
- `sample_output/okf-bundle/migration-report.{json,md}`: counts and lineage
- `sample_output/recall-parity.json`: structural and golden-QA results
- `sample_output/reexported-okf/`: output from Memanto's shipped exporter
- `sample_output/portability-parity.json`: field-level round-trip evidence
- `validate_portability.py`: reproducible official-code-path fidelity gate
- `golden_qa.json`: transparent validation contract

No API keys, private tool outputs, local usernames, or raw reasoning are
included in the repository.
