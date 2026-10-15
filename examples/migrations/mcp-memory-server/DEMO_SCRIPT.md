# Two-minute demo script

## 0:00–0:15 — The lock-in

Show `sample/source/memory.jsonl` and explain that the official MCP Memory
Server stores a useful knowledge graph, but humans see dense JSONL and the
graph stays coupled to one tool.

## 0:15–0:35 — Prove the source is real

Run:

```bash
python generate_real_source.py \
  --output /tmp/mcp-memory-demo/memory.jsonl \
  --force
```

Point out that the script launches the pinned official npm package and calls
its MCP tools over stdio; it does not fabricate the JSONL.

## 0:35–1:00 — Escape to OKF

Run:

```bash
python migrate_mcp_memory.py \
  --input /tmp/mcp-memory-demo/memory.jsonl \
  --output /tmp/mcp-memory-demo/okf
```

Open one generated entity document. Highlight readable observations, typed
links, backlinks, and the exact source block.

## 1:00–1:25 — Prove Memanto can consume it

Run:

```bash
memanto migrate okf /tmp/mcp-memory-demo/okf --dry-run

python validate_round_trip.py \
  --source /tmp/mcp-memory-demo/memory.jsonl \
  --okf /tmp/mcp-memory-demo/okf \
  --golden sample/golden_qa.json
```

Highlight the official CLI's five mapped memories, zero skipped records, the
typed breakdown, and five out of five golden phrase-retention checks. This
offline check verifies content preservation; the final live step performs the
actual retrieval and answer commands.

## 1:25–1:45 — Prove there is no lock-in

Run:

```bash
python reconstruct_mcp_memory.py \
  --input /tmp/mcp-memory-demo/okf \
  --output /tmp/mcp-memory-demo/reconstructed.jsonl
cmp /tmp/mcp-memory-demo/memory.jsonl \
  /tmp/mcp-memory-demo/reconstructed.jsonl
```

Show the zero exit code: the graph can leave Memanto again without loss.

## 1:45–2:00 — Close

For the final live take, run the guarded cloud-backed script after configuring
the API key locally:

```bash
python run_live_demo.py --agent mcp-memory-escape-demo --execute
```

Show the `recall`/`answer` output, the exported OKF folder, and
`live-round-trip.json` with matching hashes. End on:

> Your agent's graph is no longer an opaque local file. It is readable,
> versionable Markdown — and it still belongs to you.
