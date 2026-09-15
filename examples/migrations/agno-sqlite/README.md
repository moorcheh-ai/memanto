# Agno SQLite memory migration

Move one user's Agno 3.x SQLite memories through Memanto's existing OKF import
and export commands. The source database is opened read-only. This example
does not implement its own Memanto importer.

## Local adapter

From the Memanto repository root, install the repository and example dependencies
in a virtual environment:

```sh
pip install -e . agno==3.0.6 sqlalchemy==2.0.52
python examples/migrations/agno-sqlite/adapter.py /path/to/agno.db ./new-okf-bundle --user-id YOUR_USER_ID
memanto migrate okf ./new-okf-bundle --dry-run
memanto migrate okf ./new-okf-bundle --agent YOUR_AGENT
memanto memory export --okf --split file --agent YOUR_AGENT
```

An existing Memanto agent/backend is needed for the last two commands. Only
the chosen user's memories are exported; an empty user ID is rejected.
Use `--table` if the database uses a custom memory-table name.
Each export needs a new output directory so an older bundle cannot retain
deleted source memories. Import into a fresh destination agent for a snapshot;
repeated imports into an existing agent are not an incremental synchronization.

The generated bundle includes complete source records in `source-records.json`.
Both that file and the readable memories may contain private information.
The included demo uses only the explicit scenario in `demo_source.py`.

## Field mapping

| Agno field | OKF representation | Memanto import |
| --- | --- | --- |
| `memory` | Human-readable body | Content, preserved or export fails |
| `topics` | `tags` and original metadata | Tags |
| `created_at` | UTC `timestamp` plus original epoch | Created timestamp |
| `updated_at` | `x_memanto.updated_at` plus original epoch | Updated timestamp |
| `memory_id`, `user_id` | Stable hashed filename; original IDs in body metadata | Metadata remains searchable in content |
| `agent_id`, `team_id`, `input`, `feedback`, extra columns | Complete JSON metadata in body and source archive | Content |
| No source memory-type field | `type: context` | Context, without inventing semantic classification |

Scope IDs in the metadata are provenance, not destination access controls.
Import into a destination whose readers are appropriate for the selected user.

The upstream importer bounds unknown-frontmatter footers. Putting full source
metadata into an `x_agno` extension would silently shorten some values. This
adapter instead keeps the complete metadata in the body and runs the actual
Memanto loader/mapper before publishing the bundle. If Memanto would truncate
the body, export fails with an explicit error. Source text containing Memanto's
reserved OKF entry delimiter also fails explicitly.

## Reproducible live demonstration

`demo_source.py` executes Agno's real SQLite persistence API, stores four
memories, corrects a delivery schedule, and adds another user's excluded record.
This is a scripted scenario, not a historical personal archive or LLM-generated
memory session.

`run_demo.py` is intended for the accompanying isolated Docker Compose runtime.
It creates a fresh destination agent and runs the real `memanto migrate okf`
dry run, live import, semantic recall, and `memanto memory export --okf`.
It waits for the asynchronous search index before checking four golden queries.
The retrieval score measures answer-bearing content among the top three results.
Separately, `answer_checks.py` asks a real Agno agent and Memanto's live answer
endpoint the same four questions, using local Ollama `qwen2.5:1.5b` on both sides.
It checks required answer fragments, including both Markdown and CSV. These four
scenario checks do not establish general answer quality or universal recall parity.

From the repository root, reproduce with Git and Docker available:

```sh
docker compose -p agno-demo -f examples/migrations/agno-sqlite/compose.yaml build cli
docker compose -p agno-demo -f examples/migrations/agno-sqlite/compose.yaml up -d
docker compose -p agno-demo -f examples/migrations/agno-sqlite/compose.yaml exec -T ollama ollama pull nomic-embed-text
docker compose -p agno-demo -f examples/migrations/agno-sqlite/compose.yaml exec -T ollama ollama pull qwen2.5:1.5b
docker compose -p agno-demo -f examples/migrations/agno-sqlite/compose.yaml run --rm -T cli python run_demo.py
docker compose -p agno-demo -f examples/migrations/agno-sqlite/compose.yaml stop
```

Initial downloads require several GB. The Compose runtime binds the server only
to localhost and uses dedicated volumes. It does not alter host Memanto settings.
The OpenAI Python package is installed because Agno's Ollama module imports it;
all model calls in this demo use local Ollama, with no OpenAI API key.

The output includes source SQLite data, input and round-trip OKF bundles,
command logs, timings, generated answers, and `live-validation.json`. The round-trip check requires
every complete input body, including source metadata, to survive the export.

The upstream OKF CLI currently has **no `--report` option and no savings report**.
The example states that limitation rather than inventing token or latency savings.
Recorded durations are measurements of this local run, not comparative benchmarks.

## Checks

```sh
pytest examples/migrations/agno-sqlite/test_adapter.py
ruff check examples/migrations/agno-sqlite
ruff format --check examples/migrations/agno-sqlite
```

The tests use real Agno SQLite databases. They cover user separation, a corrected
source record, source immutability, epoch timestamps, Unicode, unknown columns,
long metadata, missing databases, empty selections, reserved delimiters, safe
filenames, and refusal to publish truncated memories.

## Bounty submission status

Prepared as a possible Path B entry for Memanto issue #1609 ($200 competitive
prize, deadline September 15, 2026 at 23:59 UTC). Code and local checks alone
are not a complete contest entry. Contributor onboarding and BountyHub sign-in
are complete. The implementation is submitted as
[draft PR #1952](https://github.com/moorcheh-ai/memanto/pull/1952).
A qualifying demo video, public showcase links, and a registered bounty claim
are still outstanding.
The issue asks for an agent-answer demonstration and a savings report; the current
upstream OKF reporting limitation should be disclosed and
resolved before presenting the entry as fully compliant. No contest acceptance,
award, or payment has occurred. Codex authored and tested this example with AI assistance.

The recorded four-question run passed on both sides with `qwen2.5:1.5b`. An earlier
run with `qwen2.5:0.5b` passed all source answers and three destination answers;
the destination omitted CSV. No question, required fragment, or source memory was
changed to obtain the later result. Model choice affects generated answers even
when all memory text is retained. A terminal-output replay is provided separately;
it is not a pixel capture of an interactive desktop session.
