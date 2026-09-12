# Two-minute demo storyboard

The video is mandatory for bounty eligibility. Record the terminal and the
generated Markdown files live; do not use slides as a substitute.

## 0:00–0:15 — show the lock-in

Open `sample/source/history.json`. Point out PydanticAI's nested request,
response, tool-call, tool-return, run ID, conversation ID and usage objects.
Explain that this JSON is useful to PydanticAI but is not an inspectable memory
wiki or a vendor-neutral interchange bundle.

## 0:15–0:45 — generate a real source run

```bash
python run_demo.py --work-dir ./demo-output --transcript ./demo-output/transcript.txt
```

The first stage runs an actual PydanticAI `Agent` over eight turns and two real
tool dispatches. Say clearly that the model is a deterministic `FunctionModel`
to keep the demo free of keys and spend; do not claim live LLM generation.

## 0:45–1:10 — the escape

Show the adapter summary: 20 source messages, 20 mapped memories, zero skipped,
privacy findings zero. Open several files under `demo-output/okf/memories/` and
show that the correction, tool result, deadline, and current folder are readable
Markdown with provenance.

## 1:10–1:30 — prove Memanto consumes it

Keep the `memanto migrate okf ... --dry-run` panel visible. It must say 20 OKF
nodes and 20 mapped memories. Open the mapped preview path printed by Memanto.

## 1:30–1:50 — prove ownership

Open `migration-manifest.json`, then run:

```bash
python reconstruct.py demo-output/okf --output demo-output/reconstructed.json
```

Show `matches_manifest: true`, 20 reconstructed messages, and the canonical
SHA-256. Then show the 6/6 → 6/6 golden recall parity report.

## 1:50–2:00 — close honestly

State that the committed evidence is credential-free. If you personally run a
live Moorcheh import, add that separately and show the real result. End with the
plain Markdown bundle and the phrase “your agent's memory is now yours.”

Before publishing, tag the official channels required by issue #1609 and add
the resulting public video/social links yourself. Never publish a key, private
history, or unredacted screen capture.
