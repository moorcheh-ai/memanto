# Gemini → OKF migration guide

## 1. Get your real export

Use [Google Takeout](https://takeout.google.com/). Select the **Gemini** data
sources.

Notes on what Google actually exports:

- The **"Gemini" service** export (Gems, Scheduled actions) produces only
  small HTML files — it does **not** contain conversation transcripts.
- Your Gemini **conversation history** lives under **"My Activity" →
  applications → Gemini**. Depending on your account Google may export the
  generated **images** rather than a full text transcript. If you need the
  plain-text conversation bodies, use a dedicated Gemini export extension and
  save the result as `conversations.json`.

`gemini.py` accepts a JSON export shaped as a list of conversations, each with
`id`/`conversation_id`, optional `title`, and `messages`/`chat_messages`.

## 2. Build the OKF bundle

```bash
python3 cli.py --source gemini \
    --input ./gemini_export/conversations.json \
    --output ./okf_output/gemini
```

Interactive chat selection:

```bash
python3 cli.py --source gemini \
    --input ./conversations.json \
    --interactive
```

## 3. Import into Memanto (dry run, then real)

```bash
memanto migrate okf ./okf_output/gemini --dry-run --agent <id>
memanto migrate okf ./okf_output/gemini --agent <id>
```

## 4. Close the portable loop

```bash
memanto memory export --okf -o ~/.memanto/export --agent <id>
```

See `docs/MAPPING.md` for the Gemini → OKF field mapping.
