# CrewAI → Memanto OKF Migration Showcase (Path B - Bounty #1609)

> **Prove the Freedom Loop**: CrewAI Memory → Open Knowledge Format (OKF) → Memanto

This showcase provides a production-ready migration path for **CrewAI** agents to liberate their short-term, long-term, and entity memory stores into vendor-neutral **Open Knowledge Format (OKF)** markdown bundles, and import them seamlessly into **Memanto**.

---

## 🌟 Highlights

- **Multi-Store Support**: Automatically parses CrewAI SQLite databases (`long_term_memories`, `short_term_memories`, `entity_memories`) and JSON memory dumps.
- **Categorization Engine**: Maps CrewAI memories into standard OKF memory types (`fact`, `preference`, `context`, `entity`).
- **PII & Secret Redaction**: Built-in automated scrubbing of API keys, emails, passwords, and local filesystem paths prior to export.
- **Memanto Import Ready**: Produces OKF markdown bundles with complete `okf_manifest.json` and `SAVINGS_REPORT.md` for immediate dry-run ingestion with `memanto migrate okf`.

---

## 🚀 Quick Start & Usage

Run commands from the repository root:

```bash
# Run the end-to-end migration showcase script
bash ./examples/migrations/crewai_to_okf/run_sample.sh
```

Or invoke the migration adapter directly on your own CrewAI memory export:

```bash
# From repository root
python3 ./examples/migrations/crewai_to_okf/migrate_crewai.py \
  --source ./examples/migrations/crewai_to_okf/sample_data.json \
  --output ./examples/migrations/crewai_to_okf/sample_output/okf
```

---

## 📂 Output Bundle Structure

After migration, the output directory contains:

```
sample_output/okf/
├── crewai-mem-0001.md
├── crewai-mem-0002.md
├── crewai-mem-0003.md
├── crewai-mem-0004.md
├── okf_manifest.json
└── SAVINGS_REPORT.md
```

### Example OKF Markdown Record

```markdown
---
{
  "okf_version": "1.0.0",
  "id": "crewai-mem-0001",
  "agent_id": "lead_researcher",
  "type": "fact",
  "tags": ["crewai", "fact", "okf_migrated"],
  "created_at": "2026-07-29T00:00:00Z",
  "source": "crewai_adapter"
}
---

# Knowledge Record (crewai-mem-0001)

**Agent Role**: `lead_researcher`  
**Type**: `fact`  
**Created**: `2026-07-29T00:00:00Z`  

## Memory Content

User prefers concise summary bullet points and markdown code snippets over raw JSON.
```

---

## 🧪 Testing Ingestion into Memanto

Verify the exported OKF bundle with Memanto CLI:

```bash
memanto migrate okf ./examples/migrations/crewai_to_okf/sample_output/okf --dry-run
```
