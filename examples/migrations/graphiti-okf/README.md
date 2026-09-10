# Graphiti → OKF → Memanto

> Liberate a **temporal knowledge graph** (episodes, entities, edges, `valid_at` /
> `invalid_at`) into a portable **OKF v0.2** markdown bundle your agent owns.
> Feeds `memanto migrate okf` — examples-only, no migrate-CLI fork.

**Bounty:** [Memanto #1609](https://github.com/moorcheh-ai/memanto/issues/1609) Path B  
**Identity:** OpheliaStowe3 · **Cost to reproduce:** $0 (mocks + offline seed)

## 15-minute quickstart (offline dry-run)

```bash
cd examples/migrations/graphiti-okf
python3 -m venv .venv && source .venv/bin/activate   # optional
pip install -r requirements.txt                      # pyyaml + pytest only
./run.sh
# or: python3 seed_graphiti.py && python3 export_graphiti.py && python3 adapter.py && python3 validate_roundtrip.py
```

Artifacts:

| Path | What |
| --- | --- |
| `out/graphiti_export.json` | Graphiti-shaped export (episodes/entities/edges/invalidated) |
| `out/okf-bundle/` | OKF v0.2 bundle (`okf_version: "0.2"`) |
| `out/migration_summary.json` | Counts + per-type breakdown |
| `out/validation_report.md` | Offline golden Q&A |

Preview import (optional, free Moorcheh key):

```bash
memanto migrate okf ./out/okf-bundle --dry-run
```

## Story

Travel agent **Mira** helps **Alex Rivera** over multi-week episodes: employer,
aisle-seat preference, **vegetarian → fish/poultry flip** (contradiction /
`invalid_at`), United loyalty, Denver offsite, refundable-only work fares,
receipt commitment, partner Jordan, Tokyo goal, PT instruction, delay
observation, backup Amex artifact.

## Layout

```text
graphiti-okf/
├── README.md MAPPING.md DRY-RUN.md
├── requirements.txt pyproject.toml run.sh run.ps1
├── seed_graphiti.py export_graphiti.py adapter.py validate_roundtrip.py
├── mocks/          # deterministic LLM + embedder + cross-encoder
├── fixtures/lived_in_script.json
├── tests/
└── out/okf-bundle/ # committed sample for offline review
```

## Live Graphiti (optional, still $0 APIs)

See [DRY-RUN.md](./DRY-RUN.md). Uses `graphiti-core[kuzu]` or Docker FalkorDB
plus `mocks/` so `add_episode` never calls OpenAI.

## Mapping

Full table in [MAPPING.md](./MAPPING.md). Edges are the primary durable
memories; entities become `context`; selected episodes keep policy / error beats.

## Non-goals

- No core `memanto migrate graphiti` CLI patch (avoids fighting #1882).
- No security bounty work.
- Upstream PR only after showcase validates + contributor onboard (done).
