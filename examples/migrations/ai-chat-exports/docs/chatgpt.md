# ChatGPT → OKF migration guide

## 1. Get your real export

Open [chatgpt.com](https://chatgpt.com) → profile → **Settings** → **Data
controls** → **Export data**. OpenAI emails a ZIP (up to ~24 h). Unzip; the
archive contains `conversations.json` (a tree-shaped `mapping` structure that
this adapter parses).

## 2. Build the OKF bundle

```bash
python3 cli.py --source chatgpt \
    --input ./chatgpt_export/conversations.json \
    --output ./okf_output/chatgpt
```

Interactive chat selection:

```bash
python3 cli.py --source chatgpt \
    --input ./conversations.json \
    --interactive
```

## 3. Import into Memanto (dry run, then real)

```bash
memanto migrate okf ./okf_output/chatgpt --dry-run --agent <id>
memanto migrate okf ./okf_output/chatgpt --agent <id>
```

## 4. Close the portable loop

```bash
memanto memory export --okf -o ~/.memanto/export --agent <id>
```

See `docs/MAPPING.md` for the ChatGPT → OKF field mapping.
