# Demo recording script

![Memory Escape video thumbnail](assets/memory-escape-thumbnail.jpg)

Target length: about 2–3 minutes after accelerating the local Hindsight retain
steps. Every terminal segment below is a real command, not a slide or mock.

## Storyboard

1. **The lock-in (0:00–0:20)**
   - Show the Beacon release conversations evolving across eight sessions.
   - Ask Hindsight for the current date, owner, cache TTL, and rollback rule.
   - Point out that three superseded facts remain auditable but invalidated.

2. **The escape (0:20–0:55)**
   - Run `run_demo --reset-bank --force`.
   - Accelerate only the model-processing wait; leave the command, retain
     counters, curation count, source recall, and real Memanto dry-run visible.
   - Show the 35 → 32 active + 3 archived migration summary.

3. **Memory ownership (0:55–1:20)**
   - Stop Hindsight.
   - Open one fact, one event, and one learning from `hindsight-okf/` as plain
     Markdown.
   - Open an invalidated item under `archive/` and explain why it cannot be
     silently reactivated during import.

4. **No amnesia (1:20–2:05)**
   - Run `run_roundtrip --agent <fresh-id> --output
     examples/migrations/hindsight/artifacts/beacon-live-run`.
   - Keep the real import count, indexing wait, eight-question Memanto recall,
     and source/destination parity report visible.
   - Ask for the current date, owner, TTL, and rollback policy again.

5. **Portable again (2:05–2:30)**
   - Open the Memanto re-exported OKF bundle.
   - Show that its concept count equals the import count.
   - End on `recall-parity.md`: same questions, explicit phrase rubric, raw
     retrieval evidence, no LLM self-grading.

## Accuracy notes

- Do not claim provider cost savings: the OKF importer has no `--report`
  option and the local source has no billing baseline.
- State the exact source, mapped, archived, and exported counts shown by the
  current artifacts.
- If a live run produces different Hindsight extraction counts, regenerate
  the committed artifacts before recording or quoting the totals.

## YouTube description checklist

- Link the pull request and issue #1609.
- Link/tag `https://www.youtube.com/@moorchehai`.
- State that Hindsight, Ollama, and the source demo use no paid service.
- Include the exact setup and round-trip commands from the README.
