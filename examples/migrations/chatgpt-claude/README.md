# ChatGPT and Claude Migration Example

This directory contains a complete example workflow demonstrating how to use the Memanto migration CLI to parse and ingest memory exports from ChatGPT and Claude.

## Overview

The ChatGPT adapter processes nested `conversations.json` tree structures, extracting user and assistant messages, while the Claude adapter processes flat JSON lists of chat threads. Both mappers extract `artifact`, `observation`, and `preference` semantics and package them into Memanto `MemoryRecord` objects.

## Files Provided

- **`sample_chatgpt.json`**: A minimal dummy ChatGPT export.
- **`sample_claude.json`**: A minimal dummy Claude export.
- **`sample.okf.md`**: An example Open Knowledge Format (OKF) bundle showing the mapped result.
- **`run_migration.py`**: A python script that executes the CLI migration flow using the `--dry-run` flag.
- **`evidence.md`**: Captured terminal output proving that the migrations work successfully and calculate storage savings.

## How to Run

From this directory, simply run:

```bash
python run_migration.py
```

This will invoke the `memanto` CLI internally on the dummy JSON files. Because it uses `--dry-run`, no real API calls are made, and Memanto simply processes the files, outputs a mapped preview, and generates a savings report in your `~/.memanto` directory.
