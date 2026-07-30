# Silent demo recording plan — 75 seconds

The final recording is captioned in English and contains no narration,
presenter, credentials, private emails, or simulated product claims.

| Time | Live evidence shown | Caption |
| --- | --- | --- |
| 00:00–00:12 | Generated editorial transformation plate | Your workflow ran. Keep what it learned. |
| 00:12–00:27 | n8n public-API execution rows `4`, `5`, `6` | Three real runs. Three decisions. |
| 00:27–00:43 | Field-level n8n → OKF mapping and execution provenance | Map the decision. Keep the evidence attached. |
| 00:43–01:00 | Shipped Memanto dry run, live import, and three live RAG answers | Official importer: 3 mapped, 0 skipped. |
| 01:00–01:15 | Live OKF export, three readable files, parity result | Readable. Reproducible. Portable. |

## Required proof before publishing

- The source rows must match the committed n8n export hash.
- The terminal status must come from `run_live_demo.py --execute`.
- The closing values must match `live-validation.json`.
- The public description must link PR #1729 and the official
  `youtube.com/@moorchehai` channel.
