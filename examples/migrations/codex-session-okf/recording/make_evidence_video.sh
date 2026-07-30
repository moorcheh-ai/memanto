#!/usr/bin/env bash
set -euo pipefail

recording_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out_dir="$recording_dir/output"
narration_dir="$recording_dir/narration"
ffmpeg="/root/.codex/tools/ffmpeg/ffmpeg"
tts="/root/.local/bin/edge-tts"
font="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
mono="/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
voice="en-US-AriaNeural"
durations=(12 13 14 13 14 14 14)

mkdir -p "$out_dir/frames" "$out_dir/audio"
rm -f "$out_dir/frames/concat.txt" "$out_dir/audio/concat.txt"

scene() {
  local number="$1"
  local title="$2"
  local body="$3"
  local footer="$4"

  convert -size 1920x1080 xc:'#07111f' \
    -fill '#22d3ee' -font "$font" -pointsize 30 \
    -draw 'rectangle 0,0 1920,12' \
    -annotate +110+105 'Codex session → Memanto → owned OKF' \
    -fill '#f8fafc' -font "$font" -pointsize 58 \
    -annotate +110+205 "$title" \
    -fill '#0f1f33' -draw 'roundrectangle 95,265 1825,900 24,24' \
    -fill '#dbeafe' -font "$mono" -pointsize 32 \
    -interline-spacing 14 -annotate +145+345 "$body" \
    -fill '#94a3b8' -font "$font" -pointsize 24 \
    -annotate +110+1015 "$footer" \
    "$out_dir/frames/scene-$number.png"
}

scene 01 \
  'A genuine Codex session, safely scoped' \
  'Input: Codex rollout JSONL\nRecords: 4 user/assistant messages\n\nExcluded by design:\n  reasoning · tool calls · system prompts\n  credentials · transport metadata' \
  'Public fixture · no private account data'

scene 02 \
  'Convert to human-readable OKF' \
  '$ python convert.py source-session.jsonl okf/\n\ninput_records       4\nmessage_records     4\nexported_memories   4\nskipped_private     0\n\nOutput: four portable Markdown memories' \
  'Deterministic output with source fingerprinting and redaction'

scene 03 \
  'Privacy and recall parity verified' \
  '$ pytest -q tests\n.....                              [100%]\n\nGolden questions                 3\nSource recalled                  3\nOKF recalled                     3\nExact recall parity              3\nResult                        PASS' \
  'The same answers survive conversion before any cloud write'

scene 04 \
  'Official Memanto dry run' \
  '$ memanto migrate okf ./okf --dry-run\n\nOKF nodes             4\nMapped memories        4\nSkipped                0\nType breakdown         context: 4\nWrites performed       none' \
  'Every node is mapped before live import'

scene 05 \
  'Live import into an isolated agent' \
  '$ memanto agent create codex-okf-live-…\n$ memanto migrate okf ./okf --agent …\n\nMoorcheh namespace created\nImported               4\nFailed                  0\nBatches                 1' \
  'Executed against Moorcheh cloud on 30 July 2026'

scene 06 \
  'The migrated agent recalls the answers' \
  'Question 1: reported date          FOUND\nQuestion 2: Python project           FOUND\nQuestion 3: TypeScript project       FOUND\n\nReturned memories retain OKF source,\nrole, tags, type, and provenance.' \
  'Three independent live recall queries succeeded'

scene 07 \
  'Export back to owned OKF' \
  '$ memanto memory export --agent … --okf\n\nExported memories       4\nPortable Markdown       yes\n\nFREEDOM LOOP COMPLETE\nCodex → filtered OKF → Memanto → OKF' \
  'Open source: github.com/ILoveBuns/memanto/tree/feat/codex-session-okf'

for number in $(seq 1 7); do
  index="$(printf '%02d' "$number")"
  duration="${durations[$((number - 1))]}"
  "$tts" --voice "$voice" --rate="+7%" \
    --text "$(cat "$narration_dir/$index.txt")" \
    --write-media "$out_dir/audio/raw-$index.mp3"
  "$ffmpeg" -y -v error -i "$out_dir/audio/raw-$index.mp3" \
    -af "apad=pad_dur=$duration,atrim=duration=$duration" \
    -ar 48000 -ac 2 "$out_dir/audio/scene-$index.wav"
  printf "file 'scene-%s.png'\nduration %s\n" "$index" "$duration" \
    >> "$out_dir/frames/concat.txt"
  printf "file 'scene-%s.wav'\n" "$index" >> "$out_dir/audio/concat.txt"
done
printf "file 'scene-07.png'\n" >> "$out_dir/frames/concat.txt"

"$ffmpeg" -y -v error -f concat -safe 0 \
  -i "$out_dir/frames/concat.txt" \
  -vf "fps=30,format=yuv420p,fade=t=in:st=0:d=0.4" \
  -c:v libx264 -preset medium -crf 20 \
  "$out_dir/video-only.mp4"

"$ffmpeg" -y -v error -f concat -safe 0 \
  -i "$out_dir/audio/concat.txt" \
  -c:a aac -b:a 160k "$out_dir/narration.m4a"

"$ffmpeg" -y -v error \
  -i "$out_dir/video-only.mp4" -i "$out_dir/narration.m4a" \
  -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 160k \
  -shortest -movflags +faststart \
  "$out_dir/codex-memanto-live-evidence-1080p.mp4"

printf '%s\n' "$out_dir/codex-memanto-live-evidence-1080p.mp4"
