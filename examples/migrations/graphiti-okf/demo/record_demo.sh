#!/usr/bin/env bash
# Record Memanto #1609 Graphiti→OKF demo (asciinema + mp4/gif via cast2mp4.py).
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
EXAMPLE="$(cd "$DEMO_DIR/.." && pwd)"
CAST="$DEMO_DIR/demo.cast"
MP4="$DEMO_DIR/demo.mp4"
GIF="$DEMO_DIR/demo.gif"
STEPS="$DEMO_DIR/demo_steps.sh"

cd "$DEMO_DIR"

if [[ ! -x "$EXAMPLE/.venv/bin/python" ]]; then
  echo "ERROR: expected venv at $EXAMPLE/.venv — create it first." >&2
  exit 1
fi
if [[ ! -x "$STEPS" ]]; then
  echo "ERROR: missing $STEPS" >&2
  exit 1
fi

export TERM="xterm-256color"
export COLORTERM="truecolor"
COLS=100
ROWS=32

echo "== Recording asciinema cast → $CAST =="
rm -f "$CAST"
# idle-time-limit: keep long pauses so social viewers can read
asciinema rec "$CAST" \
  --overwrite \
  --cols "$COLS" \
  --rows "$ROWS" \
  --idle-time-limit 30 \
  --env "TERM,COLORTERM,SHELL" \
  --title "Memanto #1609 Graphiti → OKF (offline + dry-run)" \
  --command "env TERM=xterm-256color COLORTERM=truecolor bash '$STEPS'"

echo
echo "== Converting cast → mp4 + gif =="
# Slightly faster than realtime for watchability (~0.85x wall → shorter video)
"$EXAMPLE/.venv/bin/python" "$DEMO_DIR/cast2mp4.py" "$CAST" --mp4 "$MP4" --gif "$GIF" \
  --fps 12 --font-size 15 --speed 0.72 --max-seconds 200

echo
echo "== Outputs =="
ls -lh "$CAST" "$MP4" "$GIF" 2>/dev/null || true
echo
echo "Replay cast:  asciinema play $CAST"
echo "Watch mp4:    open $MP4 (or ffplay)"
