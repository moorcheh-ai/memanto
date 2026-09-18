# Goose to Memanto migration report

This report is from the recorded Goose 1.49.0 session in
`fixtures/goose-session-export.json`.

## Result

- Source sessions: 1
- Source conversational messages: 6
- Source tokens recorded by Goose: 3,610
- OKF memories written: 4
- Memanto dry-run mappings: 4
- Skipped mappings: 0
- Cloud import: 4 imported, 0 failed, 1 batch
- Cloud recall: 4 memories retrieved
- Memanto OKF export: 4 memories in 14 files
- Golden recall checks: 4/4 passed
- Exported-bundle recall checks: 4/4 passed
- Python regression tests after the Goose run: 2/2 passed

## Mapping

| Goose record | OKF memory | Count |
| --- | --- | ---: |
| Session metadata and latest result | `event` | 1 |
| Initial failed test result | `error` | 1 |
| Completed fix and passing tests | `fact` | 1 |
| Retained project rules | `preference` | 1 |

## Size and runtime

- Privacy-safe source fixture: 2,918 bytes
- Generated OKF bundle: 3,623 bytes across 8 files
- Memanto-exported OKF bundle: 10,476 bytes across 14 files
- Size change: +705 bytes (+24.2%)
- Local adapter runtime on the recorded machine: 154.3 ms
- Adapter and deterministic validator model calls: 0

The bundle is larger than the compact source JSON because it adds readable
Markdown, per-memory provenance and indexes. This showcase therefore makes no
storage-savings claim. The adapter and deterministic validation run locally and
do not call a model. The complete showcase also performs one real cloud import,
retrieval and RAG answer through Memanto. The provider did not return a billable
cost for those calls, so this report does not claim a monetary saving for the
full round trip.

## Provenance

- Goose session: `20260908_6`
- Provider: `chatgpt_codex`
- Model: `gpt-5.6-luna`
- Goose version: 1.49.0
- Source database SHA-256 at export:
  `18dad60a9bcbac2732e8143640e2cc55b0b02de435aca806b0c047ffc649b079`
- Privacy-safe fixture SHA-256:
  `790fbe9f8f34f3b6c0e2130456aafe8a8a4f3a3ed1f4d4e0e625d6779dbb003f`

The committed fixture removes the Windows account name and personal email
address. The hashes document the exact local source snapshot and committed
fixture used for this report; they do not reveal the redacted values.
