# opencode → Memanto → OKF: own your assistant's memory

Coding assistants accumulate valuable project knowledge — repo conventions,
hard-won bug fixes, reversed decisions — trapped in local session storage.
This showcase migrates [opencode](https://github.com/sst/opencode) sessions
(SQLite, fully local, no API key needed) into Memanto and back out as a
portable [OKF](https://docs.memanto.ai/integrations/okf) bundle, proving the
full freedom loop: **in → owned → portable**. Bounty #1609, Path B
(unsupported source).

## Quick start (reproducible, ~2 minutes)

```bash
cd examples/migrations/opencode-memory
pip install -r requirements.txt

# 1. synthetic lived-in store (no real data touched)
python make_sample_store.py --out opencode_export.json

# ...or export YOUR sessions (read-only; tool inputs/outputs REDACTED by
# default — truncation is not redaction, so payloads are dropped unless you
# explicitly opt in with --include-tool-payloads, which may leak secrets):
python export_opencode.py --limit 20

# 2. convert to OKF
python opencode_to_okf.py --in opencode_export.json --out okf-bundle

# 3. prove zero amnesia (same questions before/after)
python check_parity.py

# 4. real import (needs a running Memanto backend)
python -m memanto migrate okf ./okf-bundle --agent demo-shop
```

## What the demo proves

| Step | Evidence |
|---|---|
| lived-in source | 3 sessions over 13 days: Tailwind convention, npm→yarn contradiction resolved, rounding bug + debugging rule |
| `migrate` path | `load_okf_bundle` + `mappers.map_okf` — the exact code path `migrate okf` uses — yields 13 rows, 0 dropped |
| OKF portability | `okf-bundle/` is plain markdown + YAML frontmatter, git-diffable |
| zero amnesia | `check_parity.py`: 6/6 recall probes pass post-migration, including the superseded npm instruction |

## Files

- `export_opencode.py` — read-only SQLite → JSON exporter
- `opencode_to_okf.py` — the adapter (see `MAPPING.md`)
- `make_sample_store.py` — synthetic fixture generator
- `check_parity.py` — before/after recall harness
- `sample-bundle/` — prebuilt OKF output for reviewers
- `MAPPING.md` — source → OKF type mapping
