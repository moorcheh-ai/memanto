# Hermes Holographic → Memanto → portable OKF

A Path B + Path C migration showcase for [Memanto issue #1609](https://github.com/moorcheh-ai/memanto/issues/1609).

This example moves a real Hermes **Holographic** SQLite memory store into a valid OKF bundle, feeds that bundle through Memanto's shipped `migrate okf` path, exports the destination back to OKF, and independently checks that the canonical Holo fields survived.

## Why this source is different

Hermes Holographic is not a flat chat export. Its source database contains canonical fact text plus trust, timestamps, tags, entity records, fact-to-entity associations, and operational feedback counters. It also contains derived FTS/HRR structures. This example makes the distinction explicit instead of pretending every byte of a vector index is portable knowledge.

**Portable source truth:** fact text, category, raw/parsed tags, trust, timestamps, feedback counters, entity records, entity associations, source fact IDs.

**Rebuilt rather than migrated:** FTS rows, HRR vectors, memory-bank vectors.

**Validated rather than fabricated:** query-time relatedness/reasoning/contradiction behavior. The public Holo schema has no durable contradiction-history or supersession table.

See [`mapping.md`](mapping.md) for the field-by-field contract.

## Reproduce in under 15 minutes

Prerequisites:

- Python supported by the current Memanto checkout;
- `uv` (recommended) or an installed `memanto` CLI;
- a local Hermes checkout containing `plugins/memory/holographic/store.py`;
- a Python environment that can run that Hermes checkout (set `HERMES_PYTHON` when needed);
- for the live write/export step only, a Moorcheh key and an existing activated Memanto test agent.

From a Memanto checkout:

```bash
uv sync --group dev
export HERMES_REPO=/path/to/hermes-agent
# Optional when Hermes uses its own virtualenv:
export HERMES_PYTHON=/path/to/hermes-agent/.venv/bin/python
./examples/migrations/hermes-holographic-to-okf/run_demo.sh
```

The default run is safe/offline except for whatever the installed Memanto CLI itself requires. It performs four acceptance-critical steps:

1. `generate_demo_source.py` creates `fixtures/memory_store.db` through the **actual Hermes `MemoryStore` public operations** (`add_fact`, `update_fact`, `record_feedback`, and, when available, `search_facts`).
2. `export_holo.py` reads that database read-only and writes `output/okf_bundle/`.
3. `validate.py` compares every portable source field against the generated Markdown and, when run inside a Memanto checkout, also passes it through the current `load_okf_bundle` + `map_okf` code path.
4. `memanto migrate okf output/okf_bundle --dry-run` exercises Memanto's shipped migration command without writes.

### Live `in → owned → portable` loop

Create/activate a disposable Memanto test agent using the normal CLI flow, then:

```bash
export HERMES_REPO=/path/to/hermes-agent
export MEMANTO_AGENT_ID=hermes-holo-bounty-demo
export MEMANTO_FRESH_AGENT_ID=hermes-holo-bounty-fresh
./examples/migrations/hermes-holographic-to-okf/run_demo.sh
```

With `MEMANTO_AGENT_ID` set, the script activates that empty test agent, imports the Holo bundle, runs all six golden recall probes, and then runs:

```bash
memanto migrate okf output/okf_bundle --agent "$MEMANTO_AGENT_ID"
memanto memory export --okf --agent "$MEMANTO_AGENT_ID" \
  --output output/memanto_roundtrip --limit 1000 --split file
```

and validates the exported destination bundle again against the original Holo SQLite store. If `MEMANTO_FRESH_AGENT_ID` is also set to a second empty agent, the script imports that exported bundle into the second agent, reruns the same six golden probes, exports again, and performs a third structural comparison. This is the full `in → owned → portable → fresh destination` proof.

## Evidence produced

`reports/` contains machine-readable evidence rather than prose-only claims:

- `source-generation.json` — exact source-tool operations and record count;
- `export-summary.json` — source count, per-type mapping, source/bundle byte accounting, and derived-data policy;
- `fidelity.json` — field-level structural fidelity result;
- `migration-report.md` — human-readable Holo-specific migration/fidelity/accounting report;
- `live-roundtrip-fidelity.json` — produced after a real Memanto write/export loop;
- `primary-golden-recall.txt` — six recall probes against the first Memanto destination;
- `fresh-destination-fidelity.json` and `fresh-golden-recall.txt` — produced when a second clean destination is supplied.

The public OKF sample lives under `output/okf_bundle/`. Open any `fact-*.md`: the memory is readable Markdown with ordinary OKF frontmatter plus a bounded YAML source-data block.

## Golden recall set

[`golden_questions.json`](golden_questions.json) contains deterministic recall probes covering preferences, source-vs-derived semantics, migration acceptance, an evolved/corrected project fact, derived-index policy, and the final portability claim. For the final bounty video, ask the same probes against Holo before migration and Memanto after migration/fresh restore and record the returned evidence. Do not substitute an LLM judge for the structural validator.

## Privacy

The committed demo corpus must contain no credentials, personal names, device identifiers, tokens, private paths, or private memory. `generate_demo_source.py` uses a sanitized technical corpus and evolves it through real Holo operations. Never commit a user's live `memory_store.db`.

## Expected fidelity claim

A correct run should support this bounded statement:

> Hermes Holographic's canonical facts, trust, timestamps, tags, provenance, and entity associations can be extracted from a real SQLite memory store, imported through Memanto, exported as portable OKF, and checked against the original source. Derived indexes are rebuilt, and source semantics that do not exist as durable records are disclosed rather than invented.

## Publication gate

Before opening a PR, run:

```bash
export DEMO_VIDEO_URL=https://...
export SOCIAL_URLS=https://...
export MEMANTO_ONBOARDING_CONFIRMED=1
python examples/migrations/hermes-holographic-to-okf/submission_gate.py
```

The gate fails closed unless the source run is pinned to a Hermes commit, the current Memanto loader/mapper has been exercised, both live destination fidelity reports pass, both golden-recall transcripts are clean, contributor onboarding is confirmed, and the required public video/social URLs exist. A green code test suite alone is intentionally not enough to authorize publication.

## Before submitting the bounty

The bounty itself additionally requires a real end-to-end video, public social link(s), and a BountyHub claim before the deadline. Those are intentionally outside this repository script. Do not open the PR until the live round-trip report and video exist.
