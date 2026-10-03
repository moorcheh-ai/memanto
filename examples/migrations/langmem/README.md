# LangMem → Memanto (OKF) migration

LangMem (LangChain's memory library) isn't one of the providers Memanto
supports out of the box. This adds one: an adapter that takes a LangMem store
and converts it into a valid OKF bundle, importable with the existing
`memanto migrate okf` command. No changes to Memanto's core needed.

Short version of what it does: populate a LangMem store with a realistic
multi-week history for a developer ("Alex") — preferences, decisions, a
correction, a stale to-do getting cleaned up — export it, convert it to OKF,
import it into Memanto, and check that recall still gives the same answers
afterward.

## Why

LangMem memories are untyped free text living in a LangGraph store. If you
want to move to a different memory layer there's currently no path out.
Adding one folder under `examples/migrations/` gives people an actual escape
hatch, and forces the mapping logic (untyped LangMem content → Memanto's 13
typed primitives) to exist somewhere reusable instead of being copy-pasted
by whoever needs it next.

## Quickstart

From the repo root:

```bash
pip install -e .
pip install -r examples/migrations/langmem/requirements.txt
cd examples/migrations/langmem
python run.py
```

No API keys needed for this. It runs five steps and writes everything to
`artifacts/`:

```
1/5  Populating a LangMem store (extract=replay)...
2/5  Exporting the LangMem store...
      -> artifacts/langmem_export.json (10 memories)
3/5  Adapting LangMem export -> OKF bundle...
      -> artifacts/okf-bundle  types: {'decision': 1, 'fact': 2, 'goal': 2, 'preference': 4, 'relationship': 1}
4/5  Validating recall parity (after=bundle)...
      before 7/7  after 7/7  parity 100.0%
5/5  Writing migration summary + mapping table...
```

Worth opening `artifacts/okf-bundle/memories/preference/` afterward — it's
just plain markdown files with frontmatter, readable without any tooling.

## What each step does

| Step | Module | What happens |
| --- | --- | --- |
| 1. Populate | `langmem_migration/populate.py` | Replays a scripted history through LangMem's `manage_memory` tool (create / update / delete), so the resulting store is a real `InMemoryStore` in LangMem's actual schema. |
| 2. Export | `langmem_migration/export.py` | Dumps `store.search()` results to `artifacts/langmem_export.json`. |
| 3. Adapt | `langmem_migration/adapter.py` + `mapping.py` | Maps each LangMem record to a Memanto memory dict and writes it out via Memanto's existing `OkfExportService`. |
| 4. Validate | `langmem_migration/validate.py` | Asks the same set of questions against the store before migration and against the migrated memories after, and compares. |
| 5. Summarize | `run.py` | Writes `migration-summary.md` and `mapping-table.md`. |

The sample history is built to actually exercise the annoying cases: a
preference that changes (pytest → Vitest, updated in place rather than
duplicated), a goal that gets descoped, a teammate who moves off the project,
and a to-do that gets deleted once it's done. If the mapping dropped or
duplicated something, the recall check would catch it.

## Importing into a live Memanto agent (optional)

Needs a free key from [console.moorcheh.ai](https://console.moorcheh.ai/api-keys):

```bash
cp .env.example .env      # add MOORCHEH_API_KEY
memanto agent create alex && memanto agent activate alex

memanto migrate okf ./artifacts/okf-bundle --agent alex

python run.py --after memanto --agent alex
```

Or in one command: `python run.py --import-memanto --after memanto --agent alex`.

## Using it on your own LangMem data

The adapter just takes an export dict, so this works against any store, not
just the sample one:

```python
from langmem_migration.export import export_store
from langmem_migration.adapter import write_okf_bundle

export = export_store(my_langmem_store, user_id="me")
write_okf_bundle(export, "./my-okf-bundle", agent_id="me")
# memanto migrate okf ./my-okf-bundle --agent me
```

Custom fields beyond `content` on a LangMem memory get preserved in a
`[Supporting data]` footer rather than dropped.

### LLM-driven extraction

Default mode replays scripted tool calls (deterministic, no keys needed). To
instead let an LLM pull memories out of the raw transcript via LangMem's
`create_memory_store_manager`:

```bash
export OPENAI_API_KEY=...
python run.py --extract live --model openai:gpt-4o-mini
```

## Mapping reference

| LangMem field | Memanto / OKF field | Notes |
| --- | --- | --- |
| `value.content` | memory body + derived `title` | kept verbatim |
| `namespace[1]` (user id) | tag `user=<id>`, `x_memanto.source=langmem` | scope preserved |
| `key` (uuid) | `source_ref` / OKF `resource` `langmem:<key>` | |
| `created_at` | OKF `timestamp` | |
| *(inferred)* | memory `type` → `x_memanto.type` | lexical classifier, same idea as the existing Mem0 mapper |
| *(constant)* | `provenance=imported`, `confidence=0.75` | |

Type is inferred since LangMem content is untyped; anything that doesn't
match a rule falls back to `observation` rather than being dropped. Full
per-memory breakdown is in `artifacts/mapping-table.md`.

## Tests

```bash
pytest examples/migrations/langmem/tests -q
```

Checks that the bundle loads back through Memanto's own `load_okf_bundle` /
`map_okf` with no memories lost, correct type/source/provenance stamping, and
full recall parity.

## Layout

```
langmem/
├── run.py
├── requirements.txt
├── .env.example
├── langmem_migration/
│   ├── conversation.py     # sample history + the recall check questions
│   ├── populate.py         # writes it into a real LangMem store
│   ├── export.py           # store -> langmem_export.json
│   ├── mapping.py          # LangMem record -> Memanto memory dict
│   ├── adapter.py          # export -> OKF bundle
│   └── validate.py         # before/after recall check
├── tests/test_adapter.py
└── artifacts/               # generated output
```

## A note on the sample data

The three-week timeline in `conversation.py` is scripted rather than
collected from a real month-long agent session — that wasn't practical to
produce for an example. What's real is that every memory in it goes through
LangMem's actual `manage_memory` tool and lands in LangMem's actual storage
schema; only the session dates are backfilled afterward in `populate.py`.
`--extract live` is there if you'd rather generate the memories with an LLM
instead of the scripted replay.
