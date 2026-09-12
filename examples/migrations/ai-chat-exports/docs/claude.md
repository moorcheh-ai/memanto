# Claude → OKF migration guide

## 1. Get your real export

Open [claude.ai](https://claude.ai) → settings/avatar → **Settings** → **Privacy**
→ **Export data**. Anthropic emails a download link (valid ~24 h). Unzip; the
archive contains `conversations.json` with your full chat history.

> Your export is the **real data** that powers this showcase. Never commit it.

## 2. Build the OKF bundle

```bash
python3 cli.py --source claude \
    --input ./claude_export/conversations.json \
    --output ./okf_output/claude
```

To pick specific chats interactively:

```bash
python3 cli.py --source claude \
    --input ./conversations.json \
    --interactive
```

To skip memories already imported (dedupe by stable `source_ref`):

```bash
python3 cli.py --source claude \
    --input ./conversations.json \
    --dedupe-from-dir ./okf_output/claude
```

## 3. Import into Memanto (dry run, then real)

```bash
memanto migrate okf ./okf_output/claude --dry-run --agent <id>
memanto migrate okf ./okf_output/claude --agent <id>
```

## 4. Close the portable loop

```bash
memanto memory export --okf -o ~/.memanto/export --agent <id>
```

See `docs/MAPPING.md` for the Claude → OKF field mapping.
