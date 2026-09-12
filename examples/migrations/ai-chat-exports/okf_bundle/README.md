# OKF bundle artifact

This folder is the **sample exported OKF bundle** required by the bounty
(see issue #1609, "OKF Artifact Included").

It is built from **real exported chat conversations** (not synthetic fixtures):
- ChatGPT — 7 neutral conversations (`source: chatgpt`)
- Gemini — 10 neutral conversations (`source: gemini`)

All memories are lightweight technical/cultural topics, selected so the sample
contains no personal identifying data. Real exported archives are **never
committed** (see `.gitignore`).

Another real-data migration (Claude, 17 conversations) was validated locally
end-to-end and reported there (recall parity + migration summary); it is not
committed here because those chats contain personal/private details.

## How it is produced

A bundle is generated from a genuine exported chat archive by running:

```bash
python3 cli.py --source <chatgpt|gemini> \
    --input ./<your_export>/conversations.json \
    --output ./okf_output/<source>
```

then the memory files are collected under `memories/<type>/` and the
`index.md` manifest is written. Claude, ChatGPT and Gemini all classify their
exported conversations as `context`, so the memories live under
`memories/context/`.

To close the portable loop on your own agent:

```bash
memanto migrate okf ./okf_output --agent <id>
memanto memory export --okf -o ./okf_bundle_export --agent <id>
```

## Layout

```
okf_bundle/
├── index.md                 # bundle manifest ("OKF Memory Bundle", 17 entries)
└── memories/
    └── context/             # one markdown memory per conversation
        └── <slug>.md
```
