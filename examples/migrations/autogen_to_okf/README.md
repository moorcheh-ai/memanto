# AutoGen → Memanto OKF Migration Showcase (Path B - Bounty #1609)

> **Prove the Freedom Loop**: AutoGen Agent State → Open Knowledge Format (OKF) → Memanto

This showcase provides a production-ready migration path for **AutoGen** multi-agent conversations, group chats, and state exports to vendor-neutral **Open Knowledge Format (OKF)** markdown bundles for **Memanto**.

---

## 🌟 Highlights

- **Multi-Agent State Parsing**: Extracts messages across `UserProxy`, `AssistantAgent`, and custom AutoGen roles.
- **OKF Type Mapping**: Maps messages into canonical types (`fact`, `preference`, `context`, `entity`).
- **PII & Credential Redaction**: Automated sanitization of API keys, emails, and filesystem paths.
- **Memanto Import Ready**: Exported OKF bundles pass `memanto migrate okf ./okf_bundle --dry-run` with 0% loss.

---

## 🚀 Quick Start

```bash
python3 migrate_autogen.py --source sample_data.json --output ./sample_output/okf
```
