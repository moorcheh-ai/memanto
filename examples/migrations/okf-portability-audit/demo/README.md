# Demo evidence

[`memanto-okf-portability-demo.mp4`](memanto-okf-portability-demo.mp4) is a
1280×720 recording of the one-command showcase running against the live public
archive for `moorcheh-ai/memanto#1609` on August 4, 2026.

Public showcase: <https://youtu.be/25Y2MVPtGzo>

The recording shows:

1. the real GitHub issue and 25 comments becoming 27 OKF memories;
2. the official `memanto migrate okf --dry-run` mapping 27 and skipping 0;
3. the production loader, mapper, type classifier, and exporter round trip;
4. the audit receipt: 27 source, 27 target, 0 removed, 0 changed; and
5. a generated memory as human-readable Markdown.

The video is silent, contains no credentials or synthetic results, and visibly
labels the implementation as AI-assisted. Re-run the same pipeline with:

```bash
python examples/migrations/okf-portability-audit/run_demo.py
```
