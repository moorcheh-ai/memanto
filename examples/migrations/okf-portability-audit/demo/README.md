# Demo evidence

## Current narrated capture

[`memanto-okf-portability-demo-v3.mp4`](memanto-okf-portability-demo-v3.mp4)
is the current continuous capture from the August 10, 2026 evidence run. It
shows 1 real issue plus 31 comments becoming 33 OKF memories, the official
dry run mapping 33 and skipping 0, a 33-to-33 lossless round trip, and 5/5
golden-question recall before and after migration. It visibly identifies PR
head `ef77062` and distinguishes generated narration from real command output.

Public showcase: <https://youtu.be/E_r7tzmHtq0>

## Previous narrated capture

Public showcase: <https://youtu.be/BRIcby6oMF4>

[`memanto-okf-portability-demo-v2.mp4`](memanto-okf-portability-demo-v2.mp4)
is the 66-second continuous version recorded from the August 9, 2026 evidence
run. It shows:

1. the real GitHub issue and 30 comments becoming 32 OKF memories;
2. the official `memanto migrate okf --dry-run` mapping 32 and skipping 0;
3. the production loader, mapper, type classifier, and exporter round trip;
4. the audit receipt: 32 source, 32 target, 0 removed, 0 changed; and
5. a generated memory as human-readable Markdown.

The video uses clean synthetic narration without music or ambient sound. It
contains no credentials or synthetic results, visibly labels the production as
AI-assisted, and displays the exact current PR head.

## Original silent capture

[`memanto-okf-portability-demo.mp4`](memanto-okf-portability-demo.mp4) is the
original 1280x720 capture from August 4, 2026. It remains available as an
archival comparison.

Original public showcase: <https://youtu.be/25Y2MVPtGzo>

Re-run the same pipeline with:

```bash
python examples/migrations/okf-portability-audit/run_demo.py
```
