ChatGPT Conversation Export — OKF Migration Adapter
===================================================

This showcase is built for the
"[BOUNTY $200] 🐜 The Great Memory Migration" bounty on the memanto repo
(https://github.com/moorcheh-ai/memanto/issues/1609).

Goal
----
Take the memory an assistant has accumulated about you inside ChatGPT —
preferences, decisions, project context, recurring problems — and liberate it
out of a proprietary chat platform into portable, human-readable Open Knowledge
Format (OKF) markdown that Memanto can import losslessly.

The adapter works in two modes:

  1. `export_and_okf.py`   — reads a ChatGPT conversation export JSON
                            (the "Export your data" JSON the OpenAI portal
                            gives you) and emits a ready-to-import OKF bundle.
  2. the OKF bundle itself   — a sample "memory of you" extracted from a
                            synthetic-but-realistic assistant chat history, so
                            the full in → owned → portable loop is reproducible
                            without touching any live account.

Source-tool concepts → Memanto / OKF mapping
--------------------------------------------
ChatGPT's exported history is a flat message log. The adapter classifies each
assistant turn by what kind of knowledge about the user it carries and maps it
onto Memanto's typed primitives:

  memory type        | when the assistant's turn says this about the user
  -------------------|--------------------------------------------------
  preference         | "...you prefer / you said you like / you want X"
  decision           | "...you decided / you chose / you'll go with"
  goal               | "...you want to build / you're working toward"
  commitment         | "...you're going to / you committed to"
  fact               | "...your job is / you're a ... / you live in"
  observation        | assistant notes user behavior / repeated pattern
  artifact           | a concrete deliverable / config / snippet the user asked for
  context            | project background the assistant should remember

Anything that doesn't fit stays typed as `observation` (Memanto auto-classifies
more granularly at import time). Every memory preserves a provenance footer
pointing back to the source message timestamp and conversation id.

Prerequisites
-------------
* A Memanto install: `pip install memanto`  (no API key needed for dry-run).
* Free Moorcheh API key at https://console.moorcheh.ai/api-keys to actually
  import (skip this for the dry-run / demo).
* Python 3.10+ (all stdlib + pyyaml, which memanto already depends on).

Quick start (single command, no account)
----------------------------------------
From the root of the memanto repo (or anywhere with `memanto` on PATH):

    cd examples/migrations/chatgpt-to-okf
    python3 export_and_okf.py --input sample_chatgpt_export.json --output okf_bundle

That writes a valid OKF bundle to `okf_bundle/`. You can then import it:

    memanto migrate okf okf_bundle              # into the active agent
    memanto migrate okf okf_bundle --dry-run    # preview before writing

Validation
----------
Run the dry-run and inspect the preview:

    memanto migrate okf okf_bundle --dry-run --preview mapped.json

Open `mapped.json` — every entry should carry `source: "chatgpt"`, a populated
`content` with a `[Supporting data]` footer, and a `type` in Memanto's fixed set.

To prove the in → owned → portable round-trip with a *live* ChatGPT export,
swap `--input` to point at your OpenAI data export's `conversations.json`:

    python3 export_and_okf.py --input ~/OpenAI/conversations.json --output my_chatgpt_okf

License
-------
MIT.
