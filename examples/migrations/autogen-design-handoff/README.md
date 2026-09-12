# AutoGen design handoff: keep the decision, keep its history

An AutoGen app can keep a useful design conversation in `ListMemory`. This
portability test explicitly clears the source after saving its snapshot; it does
not claim an AutoGen failure. This example moves an actual `ListMemory` component
snapshot through OKF into Memanto, queries the cloud copy, and exports readable
OKF again. It targets the **new adapter / workflow** paths of
[The Great Memory Migration #1609](https://github.com/moorcheh-ai/memanto/issues/1609).

The case is a fictional **Harbor reading lamp** design handoff. A superseded
graphite finish stays in the record, while the approved warm-white finish is
answered correctly. A structured JSON dimension record exercises more than
plain-text copying. All eight records are synthetic; no personal chat, production
dataset, LLM call, or paid source-provider account is involved.

## What runs

```text
8 real AutoGen ListMemory.add calls
    → query + update_context → dump_component JSON
    → bounded lossless adapter → 8 OKF Markdown nodes
    → memanto migrate okf --dry-run
    → memanto migrate okf (Moorcheh cloud)
    → memanto memory export --okf --split file
    → payload integrity audit + 6 equal-scope recall checks
    → separate informational top-3 ranking audit
```

The script invokes the shipped CLI for both migration and export. It does not
replace the migration implementation with custom upload calls. It uses Memanto's
SDK only for target-emptiness verification and actual recall queries.

## Reproduce

Python 3.10–3.12; tested with Python 3.12.12, AutoGen Core 0.7.5,
Moorcheh SDK 1.3.7, and Memanto source commit `228dddad5`.
From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e . -r examples/migrations/autogen-design-handoff/requirements.txt
python examples/migrations/autogen-design-handoff/migrate_demo.py --output /tmp/autogen-offline
pytest -q --override-ini='addopts=' examples/migrations/autogen-design-handoff/test_adapter.py
```

The offline command really seeds AutoGen, serializes it, converts it, and runs
the CLI dry run. It needs no account and performs no cloud import.

For the complete cloud run, obtain a free API key from
[Moorcheh Console](https://console.moorcheh.ai/api-keys), set `MOORCHEH_API_KEY`
privately in the process environment, then run:

```bash
python examples/migrations/autogen-design-handoff/migrate_demo.py \
  --live --output /tmp/autogen-live
```

Do not paste a key into a committed script, screenshot, shell transcript, or PR.
The run creates a uniquely named demo agent. Do not point it at production data.
It refuses to reuse an output directory or a non-empty target agent. Memanto
exports inside `~/.memanto/exports/`; the example respects that guard, then copies
only the generated demo bundle into its evidence directory. Setup plus this
eight-record run is intended to fit within 15 minutes on a working connection.

## Use your own ListMemory snapshot

Serialize your actual store with
`memory.dump_component().model_dump_json()` and save that JSON locally. Review
it for private content before choosing any cloud destination. Conversion itself
is offline:

```bash
python examples/migrations/autogen-design-handoff/convert.py my-component.json my-okf
memanto migrate okf my-okf --agent YOUR_AGENT --dry-run
# Inspect the mapped preview, then omit --dry-run to import deliberately.
```

The six Harbor questions belong only to the reproducible demo. They are not
silently applied as a benchmark to someone else's data.

## Recorded live result

The checked-in `evidence/` is from a real cloud run starting **2026-09-12 09:44:48 UTC**
(agent `autogen-handoff-20260912094448`):

| Check | Observed result |
| --- | --- |
| Source / converted / imported / exported | 8 / 8 / 8 / 8 |
| Target records before import | 0 |
| Skipped / failed imports | 0 / 0 |
| Original content + MIME + metadata multiset recovered after export | exact match |
| Equal-volume current-value recall | 6 / 6, all 8 records per query |
| Separate ranked top-3 audit | 5 / 6; review-clearance instruction missed |
| CLI dry run / import / export wall time | 0.242 s / 4.196 s / 10.814 s |
| Boundary/integrity/gate tests | 13 passed |

Inspect [migration-summary.json](evidence/migration-summary.json),
[source operations](evidence/source-operations.json),
[equal-volume recall results](evidence/recall-after.json),
[ranked top-3 results](evidence/ranked-top3.json), and
[exported OKF](evidence/exported-okf/index.md).
The source process is explicitly cleared after its snapshot is captured; the
cloud run is not reading its answers from a still-populated source object.

**This is a migration integrity and retrieval smoke test, not a general recall
benchmark.** AutoGen `ListMemory.query` returns every record chronologically; the
source answer extractor filters `metadata.status == "current"`. The main
parity audit therefore requests all eight target records and applies the same
explicit current-status rule. This tests preservation and access with equal
context volume, not ranked-search parity. A separate top-3 audit found five of
six answers: the clearance instruction was not in the returned three records.
The same limitation appeared in the previous live run; its original failed
checks and report are retained in [evidence/history](evidence/history/README.md).
We changed the audit scope, not the eight source records, questions, or expected
answers. No repeated run was selected to make the top-3 result look perfect.
Source checks, lossless export, and equal-volume recall are mandatory gates;
a failure saves evidence and exits nonzero. The ranked-top-3 result remains a
separate reported limitation. No LLM judges or generates the answers. Eight deliberately small records and six
known questions cannot establish production-scale search quality.

## Mapping and intentional boundaries

| AutoGen input | OKF / Memanto representation |
| --- | --- |
| `content`, `mime_type`, full `metadata` | canonical JSON in an `autogen-record` fenced body block |
| Source ordinal + SHA256 | deterministic filename and `resource` reference; identical repeated records remain distinct |
| `metadata.kind=decision` | `decision` |
| `metadata.kind=constraint` | `fact` |
| `metadata.kind=procedure` | `instruction` |
| Other kind | `observation` |
| Provenance | `source=autogen-listmemory`, `provenance=imported` |

The original record is stored in the body because the CLI's supporting-data
footer is bounded. The adapter validates the entire batch before writing any
node. It rejects unsupported MIME types, records over 6,000 serialized characters,
foreign components, and output-directory reuse rather than silently dropping
data. Text and JSON are supported; images, custom memory providers, and unbounded
production exports are outside this small adapter's scope.

The source's `superseded` status is application metadata, not a Memanto lifecycle
transition: both historical and current versions are imported as active memories.
The example does **not** claim that migration automatically reconciles conflicts.
It retains enough provenance to apply that policy explicitly later.

## Costs and savings

The observed account used Moorcheh's Community Plan with a 100,000-request quota.
This run used that free allocation and no paid LLM/source service. This is an
account snapshot, not a promise of future pricing. The shipped `migrate okf`
command does not produce a provider savings report. AutoGen `ListMemory` is an
in-process list, so a claimed embedding-cost reduction would be misleading.
Savings are therefore **N/A**, while measured timings are preserved in the report.

## Files

- `migrate_demo.py`: seed, adapter, actual CLI orchestration, integrity and recall audit.
- `test_adapter.py`: negative MIME/size/schema cases, no partial output, duplicate
  preservation, deterministic output, and the shipped mapper roundtrip.
- `showcase_server.py`: one-shot localhost UI that runs and displays the real CLI
  pipeline. With the same private environment, run it and open
  `http://127.0.0.1:8769/`, then click **Run live migration** once.
- `requirements.txt`: the small additional dependency set.
- `evidence/`: real source component, source operations, both OKF bundles,
  actual CLI transcripts, migration summary, six full-context and six ranked
  cloud recall responses, and the previous failed-audit history.

The example does not delete cloud agents automatically. After review, remove
only the uniquely named synthetic demo agent through Memanto or the console.
