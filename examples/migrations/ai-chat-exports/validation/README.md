# Round-trip validation

`validate_roundtrip.py` (at the bundle root, alongside
`cli.py`/`generate_report.py`) proves the "zero amnesia" claim of Path B:

1. **before** — does the raw source export answer the golden questions
   (keyword-overlap evidence directly from the real archive)?
2. **migrate** — the adapter generates OKF and `memanto migrate okf` imports it.
3. **after** — does Memanto (`memanto answer`) answer the same questions?

```bash
python3 validate_roundtrip.py \
    --source claude \
    --input ./conversations.json \
    --all \
    --output ./okf_output/claude \
    --questions "what is X?" "how to do Y?"
```

Output ends in `Recall parity: N/N`. Requires an active Memanto agent and
`MOORCHEH_API_KEY` in `.env`.

## Result on real data (Aug 2026)

With the author's genuine Claude export and 4 golden questions
(snapshot/incremental-loading, LinkedIn scraping, Python WebSocket, Clawdbot
options), the round trip returned **Recall parity: 4/4**.
