# Attention Tiles adapter — submission summary

Updated 14 September 2026 for [PR #1984](https://github.com/moorcheh-ai/memanto/pull/1984), an entry for [challenge #1609](https://github.com/moorcheh-ai/memanto/issues/1609).

When an invention catalogue moves between memory systems, a summary alone can lose its original source pointers and evidence limitations. This example adapts Voller's existing public Attention Tiles catalogue to OKF while preserving complete records, original fields, links and ordering. Memanto's shipped CLI performs import and export; reverse reconstruction and checksums detect missing or changed source data. Oversize records are rejected instead of truncated.

## Completed evidence

- [Recorded cloud run 34803196191](https://github.com/jaonnvoller-ai/memanto/actions/runs/34803196191): both migrations preserved all 66 public tiles and the catalogue metadata; both agents returned all eight expected records, each ranked first, after two successive complete native exports.
- [Real demonstration and public YouTube showcase](https://www.youtube.com/watch?v=MoRh6S9bJmo), with the [original recording and evidence artifact](https://github.com/jaonnvoller-ai/memanto/actions/runs/34803196191/artifacts/10332006209). The video has no audio.
- `sample-cloud-okf/` contains the earlier actual native export from run 34781697137; `source-okf/` supplies that run's original input files referenced by its provenance footers. Both remain byte-for-byte copies of the verified archive, with SHA-256 manifests.
- Contributor onboarding completed in [merged PR #1981](https://github.com/moorcheh-ai/memanto/pull/1981). PR #1984 is open, and BountyHub claim registration is complete. Its saved 14 September update includes the final links.

## Validation and limits

The original readiness implementation was validated with 990 passing local tests and 24 skipped live-service tests, plus pre-commit and scoped type checks. The successful cloud workflow had 49 focused checks, including nine cleanup checks. These counts describe those recorded revisions, not a new run of the complete suite. The companion CI [run 34803196275](https://github.com/jaonnvoller-ai/memanto/actions/runs/34803196275) passed lint, formatting, type checks and Python 3.10–3.14 jobs. Review-follow-up checks and any later results are recorded in the README.

Earlier immediate retrieval misses remain in the README and raw evidence. The keyword source baseline also scored 8/8. These are named-record retrieval and data-preservation checks, not general AI answer-quality evidence; no cost or latency saving is claimed. The records describe concepts and do not verify physical performance.

The maintainer's review and confirmation of custom-source eligibility under Path B or C remain outstanding. No merge, award or payment is claimed. Prepared for Jaon Voller with OpenAI Codex assistance.
