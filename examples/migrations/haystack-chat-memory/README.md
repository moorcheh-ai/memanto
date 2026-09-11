# Haystack conversation memory → Memanto → portable OKF

This example adds a migration path for the experimental Haystack `InMemoryChatMessageStore`. It exports an explicitly selected chat session, feeds Memanto's shipped OKF importer, and reconstructs the complete ordered `ChatMessage` objects from exported OKF. The procurement demo keeps corrected preferences, a system instruction, multiple text blocks, tool-call/result identity, error flags, Unicode and nested metadata.

The source is an **in-memory** store. The demo writes synthetic conversation inputs through Haystack's actual API, retrieves its messages, and saves the resulting snapshot. It does not claim a persistent store, real customer data or weeks of organically accumulated history. The experimental package was archived upstream in July 2026; the pinned versions below are a reproducible migration source, not a recommendation for a new application dependency.

## Current evidence status

The actual **on-prem** loop succeeded: 15 source messages → 15 persisted observations → 15 exported messages, exact full-object reconstruction and four real semantic-retrieval answers after the selected source session was cleared. `evidence/onprem/` contains the original source snapshot, actual Memanto-exported OKF, CLI logs and measured reports. `sample/` separately retains the local dry-run example.

The cloud attempts returned `403 Forbidden`; no cloud success is claimed. A sponsor question about cloud activation and acceptance of the supported on-prem deployment is pending. The actual terminal walkthrough is included below. The [public video demonstration](https://youtu.be/TZ-gKzbQQZE) is published; on-prem bounty eligibility has not yet been confirmed by the sponsor.

The [79.9-second walkthrough](evidence/onprem/onprem-demo.mp4) replays the actual captured terminal execution. The [recording receipt](evidence/onprem/onprem-demo.json), [original cast](evidence/onprem/onprem-demo.cast), [migration report](evidence/onprem/summary.json), [retrieval results](evidence/onprem/destination-recall.json), [runtime inspection](evidence/onprem/runtime.json) and [exported OKF](evidence/onprem/exported-okf/) accompany it. Presentation pauses are labeled and excluded from measured CLI durations.

Validation: **13 tests pass**, Ruff lint and formatting pass for all eight Python files, and mypy passes for the seven production Python files with Python 3.12 and `--follow-imports=silent`. The full repository suite was not run.

## Setup

From the Memanto repository root, with Python 3.12:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python -m pip install -r examples/migrations/haystack-chat-memory/requirements.txt
.venv/bin/python -m pytest examples/migrations/haystack-chat-memory/test_adapter.py -q
.venv/bin/python examples/migrations/haystack-chat-memory/run_showcase.py examples/migrations/haystack-chat-memory/.runs/local-1
```

This local command populates Haystack, creates the adapter bundle, invokes the shipped `memanto migrate okf ... --dry-run` command and verifies actual loader/mapper fidelity. **It does not perform cloud import or export.** Choose a new output directory for each run; evidence is never overwritten.

For the cloud loop, put your own free Moorcheh key in the `MOORCHEH_API_KEY` environment variable, then run:

```sh
.venv/bin/python examples/migrations/haystack-chat-memory/run_showcase.py examples/migrations/haystack-chat-memory/.runs/live-1 --live --agent my-unique-haystack-demo
```

The runner creates only the named dedicated agent, imports 15 observations with the shipped CLI, exports with `memanto memory export --okf --split file --limit 16`, and verifies exact structured parity. Only after successful export validation does it clear the selected synthetic source session. It then executes four actual Moorcheh semantic recall queries and applies the same deterministic latest-setting answer rule used before migration. The second source user's session remains untouched. A missing/altered/duplicate record or wrong answer fails the run.

The small `cli.py` bootstrap redirects `Path.home()` only inside its subprocess before importing Memanto, confining Memanto settings/session state to the run's `private/` directory. The runner does the same before its Memanto imports. This is needed because the current CLI lacks a global config-directory flag. It does not change the user's HOME environment or replace the importer, exporter, SDK or backend. Explicit environment variables remain inherited; run from a checkout without an unrelated project `.env`. Never commit the generated `private/` directories or API keys.

## Reproduce the supported on-prem loop (Apple Silicon)

This path uses the official ARM64 Moorcheh server, native macOS Ollama **0.34.0**, and the real **All-MiniLM** embedding weights. It needs Docker Desktop running and no paid credential. New downloads total approximately **357 MiB**: native Ollama archive 152 MiB, server compressed image 161 MiB and embedding weights 44 MiB. No generative LLM is downloaded or called. The server's unused default `qwen2.5` setting is not a loaded model.

Install the Python requirements above. From this example's directory, download and extract the [official native Ollama archive](https://github.com/ollama/ollama/releases/download/v0.34.0/ollama-darwin.tgz) into `.runs/ollama-bin/`. In a terminal, run:

```sh
mkdir -p .runs/models
OLLAMA_HOST=127.0.0.1:11435 OLLAMA_MODELS="$PWD/.runs/models" OLLAMA_NO_CLOUD=1 .runs/ollama-bin/ollama serve
```

Keep it running. In another terminal in this directory:

```sh
OLLAMA_HOST=127.0.0.1:11435 .runs/ollama-bin/ollama pull all-minilm
OLLAMA_HOST=127.0.0.1:11435 .runs/ollama-bin/ollama create all-minilm-haystack -f Modelfile
./onprem-server.sh
curl --fail http://127.0.0.1:18080/health
```

The health response must identify `all-minilm-haystack`. The supplied `Modelfile` retains the same 384-dimensional weights and sets **`num_ctx 512` and `num_batch 512`**, within the model's 512-token training context. The packaged default of 256 rejected ten source inputs (261–383 tokens) in an initial actual run; the CLI reported 15 imported while only five persisted. The strict export check caught this, and those failed recordings remain failures. No source messages were shortened or removed to make the test pass. Longer real-world histories may need a larger-context embedding model even when adapter body limits pass.

From the repository root, run:

```sh
.venv/bin/python examples/migrations/haystack-chat-memory/run_showcase.py examples/migrations/haystack-chat-memory/.runs/onprem-1 --live --backend on-prem --server-url http://127.0.0.1:18080 --agent my-unique-onprem-haystack-demo
```

Add `--demo` for a readable walkthrough with explicitly labeled presentation pauses. Those pauses are outside the measured CLI durations; the original terminal recording preserves real elapsed time. The runner waits for the real namespace count, then still requires exact export reconstruction. It exports inside Memanto's permitted data directory and copies the resulting bundle into the evidence directory; no exporter restriction is bypassed.

`onprem-server.sh` uses a dedicated named Docker volume and gives its data directory to the official container's UID/GID 65532. It refuses to replace an existing named container. When done, run `docker stop memanto-haystack-example` and stop the native Ollama terminal. Keep the dedicated volume if you want the migrated memory to persist.

## Use your own source session

Configure `InMemoryChatMessageStore(skip_system_messages=False, last_k=None)` at creation and call `retrieve_messages(your_session_id)`. Its `to_dict()` serializes constructor options, not chat history. The defaults otherwise omit system messages and retain only a recent window. Use `source_history.py` as the export hook in the process that owns your live store; do not restart an in-memory store and expect its history to persist.

Save a snapshot with `format: haystack-chat-store-v1`, a `sessions` dictionary mapping session IDs to `[message.to_dict(), ...]`, and optional generation/version metadata. Then:

```sh
python examples/migrations/haystack-chat-memory/adapter.py source.json input-okf --session your-session
memanto migrate okf input-okf --dry-run
memanto migrate okf input-okf --agent your-dedicated-agent
memanto memory export --agent your-dedicated-agent --okf --split file --limit 1000 --output exports/haystack-evidence
```

The example accepts at most 1,000 messages/session, 8 MiB snapshots and an 8,000-character canonical body per message. Oversized or unsupported content fails before publishing a partial bundle. Review private source information before uploading it. Text and serialized tool call/result content are supported; other top-level content modalities are explicitly rejected.

## Mapping and fidelity

| Haystack concept | OKF / Memanto mapping |
|---|---|
| One ordered chat message | One `observation`; no inferred facts or preferences |
| Role | Human-readable title, `role-*` tag and canonical source object |
| Selected session + position + complete message | SHA-256-derived `resource`; distinct across sessions even when source IDs overlap |
| All text blocks | Readable blockquote plus exact canonical JSON |
| Tool calls, results, IDs and errors | Complete serialized source object in canonical body |
| Nested metadata and source ID | Canonical body, avoiding bounded frontmatter footers |
| Store configuration and package versions | Source snapshot/report |
| Memanto record identity / timestamps / state | Destination-generated; original database IDs/state are not promised |

Canonical JSON escapes angle brackets so literal `<!-- okf-entry -->` in a source message cannot split an OKF record. Reconstruction anchors on unquoted wrapper lines; a quoted source snippet containing the wrapper cannot impersonate it. Before publishing the bundle, the adapter runs the actual Memanto loader and mapper and compares every reconstructed envelope with the source. The 8,000-character limit leaves space for Memanto's supporting-data footer under its 10,000-character content bound.

## Evidence and metrics

`source-snapshot.json` is an actual Haystack API snapshot; `input-okf/` is adapter output. Only `exported-okf/` from **live mode** is an actual Memanto destination export. Reports explicitly distinguish `LIVE_MEMANTO_ON_PREM` from `LIVE_MOORCHEH_CLOUD`. `summary.json` distinguishes modes, records versions, configured embedding expectations, exact counts, type breakdown, source/bundle bytes, actual CLI durations, structured parity and golden questions. `destination-recall.json` contains actual backend retrieval outcomes. The retrieval test requests up to 20 records from a 15-record corpus and resolves the latest source position; it is not a top-1 retrieval benchmark or an LLM reasoning score.

The shipped `memanto migrate okf` command has **no `--report` option and produces no savings report**. This example records measured sizes and durations separately and makes no token, storage-cost or latency-savings claim. A 0 exit code from import alone is insufficient: the exported count and exact source reconstruction are required.

A recorded execution should show source answers, CLI dry run/import/export, the source being cleared, readable exported Markdown and successful backend answers. Keep failed runs labeled as failures. A terminal replay is a replay of captured execution, not a desktop screen capture. The live evidence is included here and the [public demonstration](https://youtu.be/TZ-gKzbQQZE) shows the captured execution.

References: [Haystack store implementation](https://github.com/deepset-ai/haystack-experimental/blob/main/haystack_experimental/chat_message_stores/in_memory.py), [Memanto migration guide](https://docs.memanto.ai/cli/migrate/migrate), [OKF guide](https://docs.memanto.ai/integrations/okf).
