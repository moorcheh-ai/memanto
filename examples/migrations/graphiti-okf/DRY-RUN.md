# Dry-run notes (Graphiti → OKF)

## What "offline" means

`./run.sh` (default) runs **without** Graphiti, FalkorDB, OpenAI, or Moorcheh:

1. `seed_graphiti.py --mode offline` materializes `out/graphiti_export.json` from
   `fixtures/lived_in_script.json` (episodes + expected entities/edges/invalidations).
2. `adapter.py` emits a real OKF v0.2 bundle under `out/okf-bundle/memories/<type>/*.md`.
3. `validate_roundtrip.py` checks golden Q&A against OKF bodies.

This satisfies the local $0 reproducibility bar and produces reviewable markdown.

## Live Graphiti path (also $0 API spend)

```bash
pip install "graphiti-core[kuzu]>=0.30.0"
python seed_graphiti.py --mode live --backend kuzu
python export_graphiti.py --mode live
python adapter.py
```

Mocks under `mocks/` replace LLM/embedder/cross-encoder so `add_episode` does not
call paid APIs. Prefer Kuzu (embedded) or:

```bash
docker run -p 6379:6379 -d --name falkor falkordb/falkordb:latest
pip install "graphiti-core[falkordb]>=0.30.0"
python seed_graphiti.py --mode live --backend falkordb
```

## Memanto migrate dry-run

```bash
export MOORCHEH_API_KEY=...   # free
memanto migrate okf ./out/okf-bundle --dry-run
```

## Contradiction beat

Edge `e-veg` (vegetarian) has `invalid_at` and is listed under `invalidated`;
`e-diet-new` is the corrected preference. Adapter tags superseded edges and sets
`x_memanto.provenance=corrected` on the replacement.
