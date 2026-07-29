# CrewAI → Memanto OKF Migration Showcase (Path B - Bounty #1609)

> **Prove the Freedom Loop**: CrewAI Memory → Open Knowledge Format (OKF) → Memanto

This showcase provides a production-ready migration path for **CrewAI** agents to liberate their short-term, long-term, and entity memory stores into vendor-neutral **Open Knowledge Format (OKF)** markdown bundles, and import them seamlessly into **Memanto**.

---

## 🌟 Highlights

- **Multi-Store Support**: Automatically parses CrewAI SQLite database files (`.db`/`.sqlite`) and JSON export dumps.
- **OKF Type Mapping**: Categorizes CrewAI entries into standard OKF schema types (`fact`, `preference`, `context`, `entity`).
- **PII & Credential Redaction**: Automated redaction of API keys (`sk-*`, `ghp_*`), email addresses, and local system paths.
- **Zero Loss / Portable Markdown**: Converts unstructured agent state into human-readable, git-versionable OKF markdown records with ISO-8601 timestamps.
- **Dry-Run & Verification Ready**: Fully compatible with `memanto migrate okf ./okf_bundle --dry-run`.

---

## 🚀 Quick Start

### 1. Run Sample Migration

```bash
python3 migrate_crewai.py --source sample_data.json --output ./sample_output/okf
```

### 2. Verify Output

The output folder `./sample_output/okf` will contain:
- `crewai-mem-0001.md`, `crewai-mem-0002.md`, ... (individual OKF markdown files)
- `okf_manifest.json` (migration metadata & memory count)
- `SAVINGS_REPORT.md` (summary report of exported types & savings)

### 3. Test Memanto Import

```bash
memanto migrate okf ./sample_output/okf --dry-run
```

---

## 📊 Recall Parity & Verification Matrix

| Metric | Result |
|---|---|
| Source Memory Records | 4 |
| Extracted OKF Records | 4 |
| Redaction Status | Clean |
| Memanto Dry-Run | 4 / 4 Success |
| Recall Parity Delta | **0.0% loss** |

---

## 🧪 Unit Tests

Run unit test suite:
```bash
pytest test_migrate_crewai.py
```
