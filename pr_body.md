## What

**Path B (New Frontier)** submission for #1609 — a new migration adapter for a
source Memanto doesn't support yet: **LangGraph checkpoint stores**
(`SqliteSaver`/`checkpoints.sqlite`), explicitly called out in the bounty.

LangGraph is where a huge share of production agents actually keep what they
learn — and that memory is locked in a binary checkpoint blob. This adapter
frees it into a portable OKF bundle, consumable by the shipped CLI:

```
checkpoints.sqlite ──adapter──▶ out/okf-bundle ──memanto migrate okf──▶ Memanto
```

No core changes: the adapter *feeds* `memanto migrate okf`; it reimplements
nothing.

## Evidence

- **Real data, not toy data:** `seed_agent.py` runs a genuine LangGraph
  `StateGraph` (7 sessions, 2 threads, incl. a resolved contradiction —
  "vegetarian" → "eating meat again"), checkpointed by `SqliteSaver`. The
  resulting `checkpoints.sqlite` is committed as evidence.
- **Fidelity:** 11 source records → 11 OKF docs, `out/migration_summary.json`
  (per-type: preference 4, fact 3, constraint 2, decision 1, commitment 1).
- **Round-trip validation:** golden Q&A set — 9/9 probes answerable from both
  source store and OKF bundle (`out/validation.json`, 100% parity).
- **Shipped-tooling acceptance:** real dry-run output:

  ```
  $ memanto migrate okf out/okf-bundle --dry-run
  OKF nodes: 11 | Mapped memories: 11 (skipped 0)
  Type breakdown: auto: 2, commitment: 1, decision: 1, fact: 3, preference: 4
  ```

- **Tests:** `pytest -c pytest.ini` → **5 passed**, including a test that loads
  the bundle through Memanto's own `okf_loader` + `map_okf` and asserts zero
  dropped records and lossless extras. `ruff check`/`ruff format` clean.
- **Demo video:** `demo.mp4` (in the example dir) — terminal recording of the
  real end-to-end run: seed → migrate → validate → genuine CLI dry-run.
- **Mapping table + losslessness:** README documents LangGraph concept → OKF
  field mapping; fields with no OKF slot ride along as frontmatter extras,
  which `map_okf` preserves into `[Supporting data]`.

## Reproduce (< 15 min)

```bash
pip install -r requirements.txt
python run.py --force
memanto migrate okf out/okf-bundle --dry-run   # no API key needed
```

Live import (free key): `memanto migrate okf out/okf-bundle`

## Files

`examples/migrations/langgraph-checkpoints-to-okf/` — adapter, seeder,
validator, single-command `run.py`, tests, README, demo.mp4, committed OKF
artifact + summary/validation reports.
