# LangChain / LangGraph Memory to OKF Migration

This example showcases how to extract conversational and agentic memories from **LangChain / LangGraph** state into the open **Open Knowledge Format (OKF 0.2)** bundle, making agent memory portable and sovereign with **Memanto**.

## Features
- Parses LangChain `ChatMessageHistory` and LangGraph checkpoint exports.
- Heuristically categorizes memories into `decision`, `preference`, `fact`, and `context`.
- Generates standard OKF Markdown files with YAML frontmatter.
- Losslessly importable into Memanto via `memanto migrate okf`.

## Quick Start

### 1. Run the Migration Script
```bash
python migrate.py --input sample_history.json --output ./okf_bundle