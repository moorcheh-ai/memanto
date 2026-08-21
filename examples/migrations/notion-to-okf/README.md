# Notion → Memanto → OKF Migration

**Path B: New Frontier** — Liberate the memory your Notion workspace has built
about you. 50 million Notion users store decisions, preferences, meeting
outcomes, goals, and relationships in Notion databases. This adapter migrates
all of it into Memanto — typed, time-stamped, vendor-neutral — then exports it
as portable OKF so your agent's memory belongs to *you*.

---

## The Lock-In Problem

Your Notion workspace knows things about you that took months to accumulate:
the stack decision made in Q3, the API latency preference from a meeting, the
relationship with the technical contact who approved your PR. None of that is
accessible to your agent. This adapter closes the gap.

---

## Migration Results

### End-to-End Summary

| Metric | Value |
|---|---|
| Source databases | 4 (Research Notes, Project Decisions, Meeting Notes, Bookmarks) |
| Source pages | 12 |
| Memories mapped | **12 (100%, 0 skipped)** |
| Memory types assigned | **8** (fact, decision, preference, event, commitment, observation, relationship, goal) |
| OKF bundle files | 12 memories + 8 type-index files |
| Offline recall parity | **6/6 (100%)** |
| Unit tests | **53 passed** |
| Ruff | ✅ clean |
| mypy | ✅ clean |

### Type Breakdown

| Notion Source | Memanto Type | Count |
|---|---|---|
| Research Notes (surveys/facts) | `fact` | 2 |
| Project Decisions database | `decision` | 3 |
| Research Notes (preferences) | `preference` | 1 |
| Meeting Notes database | `event` | 2 |
| Research Notes (commitments) | `commitment` | 1 |
| Research Notes (observations) | `observation` | 1 |
| Bookmarks (people/contacts) | `relationship` | 1 |
| Research Notes (goals) | `goal` | 1 |

### Recall Parity (Offline — No API Key Needed)

`recall_parity.json` committed. Run to reproduce:

```bash
python validate_recall.py --offline
```

| Question | Type | Score |
|---|---|---|
| What decision was made about the memory backend? | decision | 1.00 |
| What is the preferred API response time? | preference | 1.00 |
| What was agreed in the Q3 planning meeting? | event | 1.00 |
| What bug was found in the datetime handling? | fact | 1.00 |
| What benchmark was used to evaluate Memanto? | fact | 1.00 |
| What is the goal for the Memanto bug bounty? | goal | 1.00 |
| **Average** | | **100.0%** |

---

## Notion → Memanto Property Mapping

| Notion Field | Memanto Field | Notes |
|---|---|---|
| `title` | `title` | Direct |
| `content` (body text) | `content` | + `[Supporting data]` footer |
| `properties.Type` | `type` | Via `NOTION_TYPE_MAP` (12 Notion values) |
| `properties.Tags` | `tags` | + `notion-db:<name>` tag appended |
| `properties.Priority` | `confidence` | Critical=0.95, High=0.9, Medium=0.8, Low=0.7 |
| `created_time` | `created_at` | ISO 8601 → UTC-aware datetime |
| `id` (Notion UUID) | `source_ref` | Back-reference to source page |
| `database` | footer | Notion database name |
| `url` | footer | Canonical Notion URL |
| `properties.Attendees` | footer | Event pages only |
| `properties.Meeting Date` | footer | Event pages only |
| `properties.Decision Made By` | footer | Decision pages only |

**Type inference fallback** (when `properties.Type` absent):

- Database name contains `"decision"` → `decision`
- Database name contains `"meeting"` → `event`
- Database name contains `"bookmark"` or `"resource"` → `fact`

**Skipped automatically:** pages with `Status: Archived / Cancelled / Trash`

---

## OKF Bundle Layout

```
sample_okf_bundle/
└── memories/
    ├── fact/
    │   ├── llm-memory-architecture-survey.md
    │   └── locomo-long-conversation-memory-benchma.md
    ├── decision/
    │   ├── switch-primary-memory-backend-from-pinec.md
    │   ├── adopt-utc-aware-datetimes-throughout-mem.md
    │   └── use-bountyhub-for-all-open-source-contri.md
    ├── preference/
    │   └── user-prefers-concise-api-responses-under.md
    ├── event/
    │   ├── q3-planning-memory-system-roadmap.md
    │   └── memanto-bounty-kickoff--issue-639-scop.md
    ├── commitment/
    │   └── agent-committed-to-shipping-temporal-rec.md
    ├── observation/
    │   └── observation-llm-judge-variance-increase.md
    ├── relationship/
    │   └── neel-moorcheh-co-founder-primary-techn.md
    └── goal/
        └── goal-win-memanto-bug-bounty-with-3-cri.md
```

Each file is valid OKF Markdown with YAML frontmatter preserving `type`,
`title`, `timestamp`, `tags`, and `x_memanto` fields for lossless
round-trip via `memanto migrate okf`.

**Bundle SHA-256:** see `migration_report.json` → `okf_bundle.bundle_sha256`

---

## Committed Evidence

| File | Contents |
|---|---|
| `migration_report.json` | Source counts, type breakdown, SHA-256 bundle hash |
| `savings_report.json` | Storage/token numbers, honest disclaimer |
| `recall_parity.json` | 6/6 golden Q&A, 100% offline recall |
| `migration_preview.json` | All 12 mapped memory payloads (dry-run output) |
| `sample_okf_bundle/` | Human-inspectable OKF Markdown, one file per memory |

---

## Setup

```bash
cd examples/migrations/notion-to-okf
pip install -r requirements.txt
cp .env.example .env
# Fill in MOORCHEH_API_KEY (free at moorcheh.ai)
```

---

## Usage

### Dry run — no API key

```bash
python populate.py --dry-run
```

Validates the full mapping pipeline, prints savings report, writes
`migration_preview.json`. Zero API calls.

### Full run — import + OKF export

```bash
python populate.py
```

Imports 12 memories into Memanto, exports OKF bundle, runs round-trip
validation.

### Live Notion fetch (your real workspace)

```bash
# Set NOTION_API_KEY and NOTION_DATABASE_IDS in .env
python populate.py --notion-live
```

### Offline recall validation — no API key

```bash
python validate_recall.py --offline
# → 6/6 (100.0%) from committed OKF bundle
```

### Live recall validation — after import

```bash
python validate_recall.py --agent notion-migration-demo
```

### Tests — no API key

```bash
pytest tests/test_notion_adapter.py -v
# 53 passed
```

### Regenerate committed evidence

```bash
python generate_migration_report.py
# → migration_report.json + savings_report.json
```

---

## Architecture

```
notion_adapter.py              ← Core mapper (stdlib only, zero extra deps)
populate.py                    ← Pipeline: load → map → import → OKF → validate
validate_recall.py             ← Golden Q&A: offline (bundle) + live (Memanto)
generate_migration_report.py   ← Savings report + SHA-256 bundle hash
data/
  notion_export.json           ← 12 pages, 4 databases (realistic sample)
sample_okf_bundle/             ← Pre-generated OKF, 8 memory types
migration_report.json          ← Committed: counts, types, SHA-256
savings_report.json            ← Committed: storage/token numbers
recall_parity.json             ← Committed: 6/6 offline recall
tests/
  test_notion_adapter.py       ← 53 unit tests, no API key required
requirements.txt
.env.example
```

---

## CLI Integration

To register as a first-class `memanto migrate notion` provider:

```python
# memanto/cli/migrate/mappers.py
from examples.migrations.notion_to_okf.notion_adapter import map_notion
MAPPERS["notion"] = map_notion
```

Then:

```bash
memanto migrate notion --file notion_export.json --agent my-agent
```

---

## Social

- X: https://x.com/chidinmaonyenwe
