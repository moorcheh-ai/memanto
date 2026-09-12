# Silent demo recording plan — 89.5 seconds

The final recording is captioned in English and contains no narration,
presenter, credentials, private emails, or simulated product claims.

| Time | Live evidence shown | Caption |
| --- | --- | --- |
| 00:00–00:12 | Generated editorial transformation plate | Your workflow ran. Keep what it learned. |
| 00:11.5–00:27 | n8n public-API execution rows `4`, `5`, `6` | Three real runs. Three decisions. |
| 00:26.5–00:43 | Field-level n8n → OKF mapping and execution provenance | Map the decision. Keep the evidence attached. |
| 00:42.5–01:00 | Shipped Memanto dry run, live import, and three live RAG answers | Imported: 3 · Failed: 0 · Q&A: 3/3. |
| 00:59.5–01:14.5 | Real recorded source command output and live-proof summary | The live pipeline is recorded; the API key is never displayed. |
| 01:14–01:29.5 | Live OKF export, three readable files, parity result | Readable. Reproducible. Portable. |

The 0.5-second overlaps are intentional transition windows between scenes. The
last endpoint, 01:29.5, matches the 89.5-second composition duration.

## Required proof before publishing

- The source rows must match the committed n8n export hash.
- The terminal status must come from `run_live_demo.py --execute`.
- The closing values must match `live-validation.json`.
- The public description must link PR #1729 and the official
  `youtube.com/@moorchehai` channel.
