# Voller Attention Tiles → portable OKF

Prepared for Jaon Voller with OpenAI Codex assistance. Status updated 14 September 2026.

An invention catalogue can lose the distinction between a proposal and a tested result when only its summary moves into a new memory system. This adapter carries each whole Attention Tile, including unknown fields, evidence limitations, original links, dates, visibility and parent relationships, into Memanto's OKF format. A reverse operation restores the source records and their order.

**Completed:** source adapter, official CLI dry-run, real Moorcheh round trips, complete cloud-export sample, contributor onboarding, recorded demonstration, public showcase, upstream [PR #1984](https://github.com/moorcheh-ai/memanto/pull/1984) and BountyHub claim registration. The [published video](https://www.youtube.com/watch?v=MoRh6S9bJmo) records actual terminal execution in [run 34803196191](https://github.com/jaonnvoller-ai/memanto/actions/runs/34803196191). Both agents preserved all 66 tiles plus catalogue metadata and retrieved all eight expected records after the independent readiness gate, each ranked first. Earlier immediate-query failures remain disclosed below. Maintainer review, custom-source eligibility and any award remain unconfirmed.

## Real source

`source_public.json` is a filtered export of Jaon's existing, saved Attention Tiles index. It contains 66 public-source records. It is not a fabricated Mem0 dump or a ChatGPT conversation export. Eleven private additions were excluded. The full 77-tile snapshot was also checked privately without loss of source fields.

The source records describe development concepts. Their inclusion does not establish physical or clinical performance, patent coverage or novelty. The upstream maintainer decides whether this custom catalogue source meets the challenge's real-source requirements.

## Run the completed local demonstration

Use Python 3.12 and a virtual environment:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run_demo.py source_public.json local-demo
.venv/bin/python -m pytest test_adapter.py -q
```

Choose a new output directory each time. The script invokes the unmodified `memanto migrate okf ... --dry-run`, maps the bundle with the shipped mapper, runs Memanto's real OKF serialization service locally, and restores every original source field. The export service receives local records; no backend is simulated or presented as a real import.

`validation.json` explicitly records that remote import and semantic recall were not tested. The bundle is larger than the compact input JSON; no compression or speed saving is claimed.

The checked-in `sample-okf/` was exported with Memanto's native serializer locally. The separate [sample-cloud-okf/](sample-cloud-okf/) contains all 67 actual memory records from the first real service export in [run 34781697137](https://github.com/jaonnvoller-ai/memanto/actions/runs/34781697137). Memory files are byte-for-byte copies. Only optional session/metrics files and their root-index links were omitted. The [provenance manifest](evidence/cloud_sample_provenance.json) records file hashes and this selection. Reconstructing either sample restores the entire public-source catalogue.

The complete original input bundle from that same archived run is now included as [source-okf/](source-okf/), with a separate [source provenance manifest](evidence/source_sample_provenance.json). A native memory's `OKF source: memories/.../<hash>.md` footer names a path relative to **source-okf/**. It is an import-provenance pointer, not a path relative to the later slug-named cloud export. For example, prepend `source-okf/` to the footer path to inspect the exact original input record. Both the original input and cloud-export memory files remain byte-for-byte copies of the verified archive. Regression checks resolve every cloud footer to its matching original JSON capsule and verify both complete snapshots and recorded file hashes.

The native export's confidence values are importer defaults, not measured support for the invention claims. Their original evidence status remains in each source capsule.

## Field mapping

| Source | OKF / Memanto representation | Recovery |
|---|---|---|
| Each invention tile | One `artifact` memory | Complete source JSON capsule |
| Catalogue metadata | One `context` memory | Complete source JSON capsule |
| ID and list position | Hashed safe filename, capsule ID and ordinal | Original ID and order restored |
| Title | Searchable frontmatter title, maximum 100 characters | Unshortened title retained in capsule |
| Summary, evidence, parent, source pointers and additional fields | Human-readable JSON in memory content | Exact JSON values restored |
| Snapshot date | Original field inside capsule | Not relabelled as a precise observation time |
| Conversion timestamp | `generated.at` | Identifies conversion, not invention creation |
| Integrity | Per-record and whole-snapshot SHA-256 | Detects missing/changed records; not authentication |

Memanto bounds supporting-data footers and content length. To avoid silent source loss, the adapter keeps the complete record inside the main body and rejects bodies over its conservative size limit. It escapes delimiter-like source text and refuses duplicate IDs or an existing output directory. It does not execute source instructions.

## Continue with the real service

Configure Memanto with an authorised Moorcheh service through its normal setup. The following command creates two fresh demo agents and uploads only the public-source selection:

```sh
.venv/bin/python run_live.py source_public.json live-demo --upload-public-source
```

The runner uses the shipped import/export CLI, exports in Memanto's approved directory with a per-type limit derived from the full expected record count (tiles plus one catalogue record), and reconstructs the entire source from both exports. Eight named-record retrieval probes compare a local keyword baseline with each Memanto agent. This is a narrow retrieval check, not an LLM answer-quality or reasoning benchmark. No source or remote agent is deleted.

### Readiness protocol v3

[Moorcheh documents text upload as asynchronous](https://docs.moorcheh.ai/python-sdk/data/upload-text). Import acceptance therefore does not establish retrieval readiness. Before scoring, the default runner requires two successive native exports to reproduce the full source digest. It allows at most eight export attempts, two seconds between attempts, with a 90-second budget checked between commands and a separate 120-second CLI timeout. It retains every snapshot and readiness observation. Authentication and CLI errors stop immediately.

The scored questions are not used to decide readiness. Each is asked exactly once per agent after the gate; any missing expected record still fails. Full export visibility is an application-level gate, not a guarantee of semantic retrieval quality. Local regression tests cover incomplete exports, reset of consecutive matches, time/attempt limits, immediate command failure and a scored miss that is not retried.

To reproduce the older diagnostic protocol explicitly, add `--diagnose-immediate`. It retains immediate scores and one later pass; early misses still fail. Historical failed runs remain failed. The v3 readiness runner completed its first successful live service run on 13 September 2026.

### Observed live results

Both imports in the verified earlier archive report **67 imported, 0 failed, 0 skipped**: 66 artifact memories and one catalogue context memory. See the [raw import summary](evidence/cloud_import_summary.txt). Both exports reconstruct all source fields with canonical SHA-256 `b17e0beea4e41398da496e3b78d4625ee4c149fd33a14c292247fa7d64d7e5cc`.

| Run and stage | First agent | Second agent | Complete source preserved |
|---|---|---|---|
| 34781697137, immediate retrieval | 6 / 8 | 8 / 8 | Both exports |
| 34784846111, immediate retrieval | 7 / 8 | 5 / 8 | Both exports |
| 34784846111, after verified export | 8 / 8 | 8 / 8 | Both exports |
| 34788286157, v3 after two consecutive complete exports | 8 / 8 | 8 / 8 | Both exports |
| 34803196191, recorded v3 demonstration | 8 / 8 | 8 / 8 | Both exports |

[Diagnostic run 34784846111](https://github.com/jaonnvoller-ai/memanto/actions/runs/34784846111) exited 1 under its strict rule requiring every stage to pass. All 16 later probes ranked their expected record first. The [32 recorded observations](evidence/live_34784846111.json) were independently parsed from its completed job log. Queries changed from misses to hits on the same agent without application-level rewriting or reimport, supporting a transient readiness explanation; they do not establish a universal delay or backend root cause.

[Successful run 34788286157](https://github.com/jaonnvoller-ai/memanto/actions/runs/34788286157) used runner commit `9a821ca9b08673b570a63de7c23524600516a3e5`. The first agent's two exports were complete; the second agent's first export was incomplete, followed by two complete exports. The retained readiness observations reached the gate at 13.069 and 19.064 seconds respectively. These are observations from this run, not promised waiting times. All 16 scored queries were asked once and ranked the expected record first. The [structured evidence](evidence/live_34788286157.json) includes every readiness and recall observation parsed independently from the completed job log, with recomputed scores and artifact references. Both full reconstructed source digests matched. The live artifact's ZIP digest is GitHub-reported; its bytes were not independently fetched into the review workspace.

The first v3 attempt, [34787075127](https://github.com/jaonnvoller-ai/memanto/actions/runs/34787075127), stopped before import because the five-namespace account limit was reached. Before the successful run, the owner approved deleting exactly the two old disposable agents from run 34781697137. The automation verified each current set of 67 documents against the archived native document hashes, uploaded fresh backups, rechecked both snapshots and removed only that approved pair. It confirmed two free slots before creating the new agents. The earlier saved export sample remains available. This cleanup was separate from the adapter and is not a general deletion policy; the live runner still creates two fresh agents on each invocation.

The full local suite recorded after the original readiness change passed **990 tests**, with **24 skipped** service tests and one existing dependency deprecation warning. All pre-commit hooks and scoped mypy checks passed. The successful manual run also passed **49 focused tests**, including nine cleanup checks, in its separate local job.

Review follow-up on 14 September passed **47 offline tests**: the adapter/runner/sample regressions plus the upstream OKF and migration tests. Ruff lint and formatting checks passed, and scoped mypy checks found no issues in the two runtime source files. The new export regression covers 0, 2, 100, 101 and 150 tiles with the actual native serializer; sample regressions verify both archived snapshots and all 67 provenance pointers. These checks use no service credentials. The prior cloud recording tests the original runner; the catalogue-sized export-limit change has been verified offline, not by creating another pair of service agents.

The official OKF command does not produce a provider savings report or accept `--report`. Do not invent one. Record actual measurements separately and retain the import summaries and limits.

## Entry status and remaining decisions

The [challenge](https://github.com/moorcheh-ai/memanto/issues/1609) requires a real completed migration, recall evidence, an exported sample, live demo video, public showcase, a pull request and a linked BountyHub claim. Deadline: 15 September 2026 at 23:59 UTC. The $200 is for the top submission, not every passing implementation. [Contribution onboarding](https://github.com/moorcheh-ai/memanto/blob/main/CONTRIBUTING.md) is also required.

The real demonstration and public showcase are published at [YouTube](https://www.youtube.com/watch?v=MoRh6S9bJmo). [PR #1984](https://github.com/moorcheh-ai/memanto/pull/1984) is open; its saved 14 September update includes the video and run links and confirms BountyHub claim registration. Contributor onboarding was completed in [merged PR #1981](https://github.com/moorcheh-ai/memanto/pull/1981). The [recording evidence artifact](https://github.com/jaonnvoller-ai/memanto/actions/runs/34803196191/artifacts/10332006209) retains the actual run and recording. The video has no audio. A workflow result or static replay is not the video evidence.

The maintainer still needs to assess the changes and confirm whether this custom catalogue with a keyword source baseline qualifies under Path B or C. No merge, eligibility decision, award or payment is claimed. [PR_DRAFT.md](PR_DRAFT.md) is now a dated submission summary; [DEMO_SCRIPT.md](DEMO_SCRIPT.md) retains the preparation outline.

Sources: [OKF documentation](https://docs.memanto.ai/integrations/okf), [Migration CLI](https://docs.memanto.ai/cli/migrate/migrate). Dependencies are pinned to upstream commit `aa3f6f1f4509dd09702679d96ce28cb0f4ac9fe3` for reproducibility.
