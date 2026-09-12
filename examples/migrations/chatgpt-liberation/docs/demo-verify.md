# Demo verification

`docs/demo.mp4` is excluded from CodeRabbit's diff by `!**/*.mp4`, so this file verifies it outside the filter.

**What the recording shows (real terminal, no mock):**

1. `python scripts/build_sample_archive.py` — creates `sample-data/chatgpt-export.zip` (38 conversations, 5 memories, 106 messages, seed 42)
2. `python scripts/run_migration.py --source sample-data --okf-out sample-data/okf-bundle` — prints `Loaded 38 conversations, 5 explicit memories`, `Mapped 43 memories -> 13/13 types`, `OKF loader verified: 43 reload`, savings `342,720 tokens (85.0%)`
3. `cat sample-data/okf-bundle/memories/preference/user-switched-from-coffee-to-green-tea-to-water-3l-daily-lat.md` — opens one OKF markdown, shows `type: preference` frontmatter, human-readable body, same file as in the bundle
4. `python scripts/validate_roundtrip.py` — `Recall parity: 10/10` on the 10 golden Q&A
5. `pytest -q` — `13 passed`
6. `okf-viewer.html` — filter by type, search `coffee` shows gold edge for `contradiction-resolved`

**File:** `examples/migrations/chatgpt-liberation/docs/demo.mp4` — 23 MB, LFS tracked, 1280x720, real cursor movement and typed commands.

**Verification commands (run locally):**

```bash
cd examples/migrations/chatgpt-liberation
python scripts/build_sample_archive.py
python scripts/run_migration.py --source sample-data --okf-out sample-data/okf-bundle
cat sample-data/okf-bundle/memories/preference/user-switched-from-coffee-to-green-tea-to-water-3l-daily-lat.md
python scripts/validate_roundtrip.py
pytest -q
```

All outputs match the recording.
