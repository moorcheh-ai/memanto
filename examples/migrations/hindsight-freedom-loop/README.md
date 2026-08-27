# Hindsight → Memanto → OKF freedom loop (#1609)

Path **B** migration adapter for [Hindsight](https://hindsight.vectorize.io/) memory banks.
Converts a Hindsight **document-transfer ZIP** (the archive from
`POST /v1/default/banks/{bank_id}/document-transfer/export`) into an
[Open Knowledge Format](https://docs.memanto.ai/integrations/okf) bundle you can
import with:

```bash
memanto migrate okf ./sample-data/okf-bundle --agent-id project-atlas-agent
```

## Why Hindsight?

ChatGPT/Claude export adapters are crowded in other #1609 submissions. Hindsight
is explicitly listed in the bounty brief as an unsupported source, ships a
documented ZIP schema, and represents agent memory that is expensive to
re-extract (facts, entities, causal links, observations).

## Quick start (< 15 minutes)

```bash
# From repository root, with memanto installed editable:
pip install -e .

cd examples/migrations/hindsight-freedom-loop

# 1) Build reproducible sample Hindsight export (schema-accurate)
python build_sample_archive.py

# 2) Convert to OKF + run golden Q&A validation
./run.sh          # Linux/macOS
# or
powershell -File run.ps1   # Windows
```

`run.sh` / `run.ps1` will:

1. Build `sample-data/project-atlas-agent.zip`
2. Write `sample-data/okf-bundle/` via `hindsight_mapper.py`
3. Run pytest for the adapter
4. Run golden Q&A recall validation
5. Print a migration summary you can paste into your PR

### Import into Memanto (optional, needs Moorcheh API key)

```bash
export MOORCHEH_API_KEY=your_key
memanto migrate okf ./sample-data/okf-bundle --agent-id project-atlas-agent --dry-run
memanto migrate okf ./sample-data/okf-bundle --agent-id project-atlas-agent
memanto memory export --okf --agent-id project-atlas-agent
```

## Mapping table

See [MAPPING.md](./MAPPING.md) for Hindsight → Memanto → OKF field mapping.

## Demo video (required for bounty)

Record a screen capture showing:

1. `build_sample_archive.py` creating the Hindsight ZIP
2. `run.sh` producing the OKF bundle
3. Opening a `.md` memory file in the bundle (human-readable markdown)
4. (Optional) `memanto migrate okf` dry-run + import

Post the video on X/YouTube/LinkedIn tagging **@moorcheh_ai** and claim on
[BountyHub](https://www.bountyhub.dev/en/bounty/view/b21928e9-70dd-4d95-adc6-3009df47e9f5).

## Files

| File | Purpose |
|------|---------|
| `hindsight_mapper.py` | ZIP parser + OKF exporter |
| `build_sample_archive.py` | Reproducible sample bank generator |
| `validation/golden_qa.json` | Recall parity questions |
| `validation/validate_roundtrip.py` | Keyword-based parity scorer |
| `sample-data/` | Generated ZIP + OKF bundle (after `run.sh`) |

## Claim checklist (#1609)

- [ ] PR adds this folder under `/examples/migrations/`
- [ ] Demo video link in PR description
- [ ] Social post links (X / YouTube / LinkedIn)
- [ ] Migration summary + sample OKF bundle in PR
- [ ] BountyHub claim before **Aug 31, 2026 23:59 UTC**
