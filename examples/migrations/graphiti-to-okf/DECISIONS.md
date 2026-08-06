# Decisions made overnight (no user present)

1. **Primary import path = OKF bundle, not provider-JSON.**
   The CLI has no `graphiti` provider. Emitting Mem0-shaped JSON would let
   `memanto migrate mem0 --file` consume the data, but `map_mem0` hard-codes
   `source="mem0"` and `confidence=0.8`, erasing Graphiti provenance and the
   temporal-standing confidence. OKF is the only import path that survives
   the trip with those intact. Provider-JSON is still emitted, but only so
   the Mem0-wired savings report can run.

2. **Preferred Graphiti backend = Neo4j via `docker compose`.**
   Matches Graphiti's own docs. FalkorDB is documented as an alternative.
   `kuzu` is kept as a zero-Docker fallback because this overnight machine
   has no Docker daemon and the JDK install needed for a native Neo4j
   hung; Kuzu is deprecated upstream but still produces a real Graphiti
   graph with real `valid_at`/`invalid_at` fields.

3. **Confidence is derived from temporal standing, not invented.**
   Current edges = 0.9, superseded = 0.5, entity nodes = 0.8, episodes = 0.7,
   communities = 0.6. Graphiti stores no per-fact score; inventing one would
   be fabrication.

4. **`valid_at` wins over `created_at` for Memanto `timestamp`.**
   Valid time is the date the knowledge was true; transaction time is when
   the pipeline ran. Preferring valid time is what makes "when did I change
   my mind" answerable after migration.

5. **Golden Q&A answers from Graphiti are pure search hits, not a second LLM.**
   The "before" side must be Graphiti's knowledge, not a chat model's
   paraphrase of it. Composing the ranked `EntityEdge.fact` lines (with
   temporal stamps) is the honest before-side.

6. **Mem0 consolidation reuses the same person/project (Daniel / Atlas).**
   So the merge is a real consolidation of overlapping sources, not two
   unrelated dumps glued together. Includes one mid-store correction
   (Friday → Monday changelog) so Mem0 itself has temporal tension.

7. **Folder name = `examples/migrations/graphiti-to-okf/`.**
   Matches the bounty prompt exactly. `/examples/migrations/` did not exist
   on `main` at time of writing; this PR creates it. Layout mirrors the
   existing `examples/benchmarks/*` convention (README + requirements +
   `.env.example` + scripts + data + tests).
