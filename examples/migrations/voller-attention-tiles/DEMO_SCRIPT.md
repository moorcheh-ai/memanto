# Live demonstration and submission handoff

Status: recording outline, not a recorded demonstration or submitted entry.

Technical validation is complete: [run 34788286157](https://github.com/jaonnvoller-ai/memanto/actions/runs/34788286157) passed the v3 protocol with full data preserved and 8/8 named-record retrieval on both agents. No additional workflow run is needed to establish that result. A new recording must show an actual run, and creating its two new agents requires available account capacity; the approved cleanup only covered the two older copies already removed.

## Record the actual pipeline

Use a screen recorder on the computer running Memanto. Configure the service key privately before recording; never show the key, configuration file or secret settings. Keep the original recording if editing it into a shorter cut. Do not stage memory loss by deleting the real source.

1. Open `source_public.json` and show the existing Attention Display or AI Fisherman tile, including its evidence limitations. Explain: “This is my saved custom catalogue of 66 public Attention Tiles.” It is not a ChatGPT export or another provider's memory dump.
2. In the terminal, from this folder with the README's virtual environment configured, run the actual command below. Show the command starting, real import/export progress and readiness observations. Use a new output folder for every run.

   ```sh
   .venv/bin/python run_live.py source_public.json recorded-live --upload-public-source
   ```

3. Open `recorded-live/02_preview.txt` and `recorded-live/03_import.txt`. Read the actual imported, failed, skipped and per-type counts. Show that these are outputs of the shipped CLI.
4. Open a memory Markdown file inside `recorded-live/first_export/memories/`. Show the original source capsule, including links and evidence status. Explain that the bundle can be inspected and reimported.
5. Open `recorded-live/live_validation.json`. Show the full-data comparison and the same eight source/first-agent/second-agent queries and returned record IDs. Report the results actually produced. These are named-record retrieval probes; do not present them as generated answers from an LLM.
6. Explain the measured limit: “The earlier diagnostic had immediate misses, then 8/8 after full export verification on both agents. This version checks complete export visibility before one scored pass. It still fails on any scored miss.” If this new run fails, show that failure and keep the artifact.
7. State: “The pinned OKF migration command has no provider savings report or `--report` option. No token, latency, cost or compression saving is claimed.” Show `evidence/validation.json` only as the measured local format report, not a provider savings report.

The challenge also asks for source-agent answers and a compelling memory-loss demonstration. This catalogue's source baseline is a keyword lookup, so explain that limitation and ask the maintainer to confirm this custom-source showcase's eligibility. Do not invent a previous source agent or manufacture source history.

A phone recording of downloading an artifact is not the live terminal demonstration described above. A recording of GitHub Actions running is real workflow footage, but acceptance as the required live CLI demonstration has not been confirmed. A recording cannot be reconstructed from past logs and labelled live.

## Entry checklist

| Requirement | Status |
|---|---|
| Source adapter, mapping, reproducible commands | Included |
| Genuine source and complete-data round trip | Included; custom-source eligibility needs maintainer review |
| Actual exported OKF sample and raw summary | Included |
| Measured recall | Included, with all early misses disclosed |
| New v3 readiness service run | Passed: run 34788286157, 8/8 on both agents, full source preserved |
| Real end-to-end recording URL | Pending |
| Public showcase URL with required Moorcheh tag | Pending |
| Upstream contribution PR URL | Pending; connected app previously returned HTTP 403 |
| Linked BountyHub account and claim | Pending |
| Repository star | Unverified |

The [official challenge](https://github.com/moorcheh-ai/memanto/issues/1609) offers **US$200 to the top entry**, with all submission components due **15 September 2026, 23:59 UTC**. This is not a guaranteed payment.

Use the same GitHub identity, `jaonnvoller-ai`, for the contribution and the BountyHub account. BountyHub's [claim instructions](https://www.bountyhub.dev/en/docs/claim-bounty) require a PR URL. A code push does not create that claim.

## Public description draft

Publish only with the real recording attached and the actual result visible:

> I am building a portable home for my Attention Tiles with Memanto and OKF. The adapter preserved all 66 public catalogue records through real service import, export and reimport, including original links and evidence limitations. Earlier tests exposed immediate retrieval misses. The revised version checks complete export visibility before one scored pass: all eight named-record probes passed on each agent in run 34788286157. The code, exported Markdown and limitations are available for inspection. This is a retrieval and data-portability demonstration. @moorcheh_ai

For YouTube, include https://www.youtube.com/@moorchehai in the description. For LinkedIn, tag the official Moorcheh AI company page. Keep the recorded result distinct from any earlier run cited for context.
