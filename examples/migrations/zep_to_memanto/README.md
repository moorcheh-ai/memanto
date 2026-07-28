# Zep → Memanto Migration Adapter

Migrate your agent's accumulated knowledge from [Zep](https://www.getzep.com/) (or Graphiti) into Memanto's portable OKF format. Proves the full freedom loop: **Zep → owned → portable**.

## What gets migrated

| Zep concept | Memanto type | Notes |
|---|---|---|
| Facts | `fact` / `preference` / `decision` | Preserves category, score, validity window |
| Graph entities | `fact` | Preserves attributes, type, group |
| Graph relations | `relationship` | Preserves source→target, episodes |
| Messages (opt-in) | `event` | Raw conversation turns, high volume |

All Zep metadata (UUIDs, timestamps, episode references, groups) is preserved in OKF frontmatter and supporting-data footers — nothing is lost.

## Quick start

```bash
# 1. Export from Zep (via API or dashboard)
#    The adapter accepts the standard Zep memory JSON format.

# 2. Convert to OKF bundle
python convert.py --input zep_export.json --output ./okf_bundle

# 3. Import into Memanto
memanto migrate okf ./okf_bundle --agent my-agent

# 4. Verify recall parity
memanto memory search "What database does the team use?" --agent my-agent
```

## Live migration (no export file needed)

If you have a running Zep instance, the adapter can fetch memory directly:

```bash
python convert.py --from-api --zep-url http://localhost:8000 --user-id user-123 --output ./okf_bundle
```

## Options

| Flag | Default | Description |
|---|---|---|
| `--input`, `-i` | `zep_export.json` | Path to Zep export JSON |
| `--output`, `-o` | `./okf_bundle` | Output OKF bundle directory |
| `--include-messages` | off | Include raw conversation messages |
| `--from-api` | off | Fetch from live Zep instance |
| `--zep-url` | `http://localhost:8000` | Zep server URL |
| `--user-id` | — | Zep user ID (required with `--from-api`) |

## Sample data

`sample_zep_export.json` contains a realistic 5-fact, 3-entity, 3-relation export demonstrating all supported fields. Run the converter on it to see the output:

```bash
python convert.py --input sample_zep_export.json --output ./demo_bundle
cat demo_bundle/memories/facts_001.md
```

## How it works

1. **Facts** → individual OKF entries with type derived from Zep's `type` field; Zep's `category` is preserved as a tag. Confidence derived from Zep's relevance score.
2. **Entities** → OKF entries preserving the knowledge graph node's summary, type, and structured attributes.
3. **Relations** → `relationship`-typed entries encoding the source→type→target triple with episode provenance.
4. **Grouping** → entries are organized into `facts_*.md`, `relations_*.md` files (20 entries each) for browsability.
5. **Losslessness** → Zep UUIDs, validity windows, episode references, and group membership are all preserved in `x_memanto` frontmatter and supporting-data footers.

## Exporting from Zep

### Via API (recommended)

```bash
# Get memory (facts + context)
curl http://localhost:8000/api/v2/users/{user_id}/memory > memory.json

# Get knowledge graph (entities + relations)
curl http://localhost:8000/api/v2/users/{user_id}/graph > graph.json
```

Merge the two JSON files, or use `--from-api` mode which does this automatically.

### Via Python SDK

```python
from zep_cloud.client import Zep

client = Zep(api_key="your-key")
memory = client.memory.get(session_id="session-1")
# Serialize to JSON and pass to convert.py
```
