# Memanto #1609 — Graphiti → OKF demo recording

Short offline CLI showcase for [PR #1958](https://github.com/moorcheh-ai/memanto/pull/1958) / issue **#1609**.

No Moorcheh live API key is required: the demo runs the example’s offline seed→export→adapt→validate loop, then `memanto migrate okf … --dry-run`.

## Artifacts

| File | Description |
|------|-------------|
| `demo.mp4` | Preferred upload format (~1 min, H.264) |
| `demo.gif` | Lightweight social preview |
| `demo.cast` | Asciinema v2 recording (replayable) |
| `demo_steps.sh` | Scripted terminal steps shown in the recording |
| `record_demo.sh` | Re-record + convert helper |
| `cast2mp4.py` | Local cast → PNG frames → mp4/gif (pyte + Pillow + ffmpeg) |

## How this recording was made

On the Cursor box (Linux, `ffmpeg` + `asciinema` + `xfce4-terminal` available):

1. Ensured `examples/migrations/graphiti-okf/.venv` had `memanto` and the offline pipeline deps.
2. Wrote `demo_steps.sh` to:
   - `cd` into `examples/migrations/graphiti-okf` and activate `.venv`
   - run `./run.sh offline`
   - show `out/migration_summary.json` and `out/validation_report.md`
   - run `memanto migrate okf ./out/okf-bundle --dry-run`
   - list and `head` a few OKF memory `.md` files
3. Recorded with:
   ```bash
   bash /workspace/memanto-1609/demo/record_demo.sh
   ```
   which wraps:
   ```bash
   asciinema rec demo.cast --cols 100 --rows 32 --idle-time-limit 30 \
     --command "env TERM=xterm-256color bash demo_steps.sh"
   python3 cast2mp4.py demo.cast --mp4 demo.mp4 --gif demo.gif --fps 12 --speed 0.72
   ```
4. Playback speed `0.72` keeps the watchable length near **~60–70s** so viewers can read the dry-run output.

### Replay / re-record

```bash
# Replay terminal session
asciinema play /workspace/memanto-1609/demo/demo.cast

# Re-record from scratch (overwrites cast/mp4/gif)
bash /workspace/memanto-1609/demo/record_demo.sh
```

Optional alternate capture (true X11 screen grab of a terminal window), if you want a desktop chrome look:

```bash
# Example sketch — not used for the checked-in artifact
DISPLAY=:4 xfce4-terminal --geometry=120x35 -e 'bash /workspace/memanto-1609/demo/demo_steps.sh' &
ffmpeg -f x11grab -video_size 1280x800 -framerate 15 -i :4 -t 90 -c:v libx264 demo-x11.mp4
```

## Suggested narration beats (social upload)

Keep VO / captions aligned with on-screen steps (~1 minute):

1. **0:00 – Hook** — “Portable agent memory: Graphiti graph → OKF → Memanto, fully offline.”
2. **0:08 – Pipeline** — “One script seeds a Graphiti-shaped export, adapts it to OKF, and validates round-trip.”
3. **0:20 – Summary** — Call out mapped node counts / type breakdown from `migration_summary.json`.
4. **0:30 – Validation** — “Eight offline checks green — structure preserved.”
5. **0:38 – Dry-run import** — “`memanto migrate okf --dry-run` previews the Memanto mapping with zero writes and no live key.”
6. **0:50 – Sample memories** — Point at preference / goal / relationship markdown (aisle seat, Tokyo goal, Cascadia Labs).
7. **0:58 – CTA** — “Try the example under `examples/migrations/graphiti-okf` — PR #1958.”

### Caption-friendly one-liner

> Graphiti → OKF → Memanto dry-run in under a minute — offline freedom loop, no API key.

## Notes

- Do **not** invent YouTube/X post URLs for this artifact; publish first, then link.
- Paths assume the worktree layout under `/workspace/memanto-1609/` (example mirrored from the PR branch).
