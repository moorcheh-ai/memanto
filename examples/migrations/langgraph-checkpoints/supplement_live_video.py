"""Append a real, hash-audited OKF Markdown inspection to a verified live cast."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from record_live_terminal import (
    CYAN,
    GREEN,
    WHITE,
    Event,
    _clean,
    _render,
    resolve_venv_python,
)

ROOT = Path(__file__).resolve().parent


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def append_inspection_events(
    events: list[Event], output: str, *, command_label: str
) -> list[Event]:
    """Return a new timeline with clearly labeled, actual inspection output."""
    combined = list(events)
    at = max(event.at for event in combined) + 0.8
    combined.append(Event(at, "POST-RUN ARTIFACT INSPECTION  |  frozen verified export", CYAN))
    at += 0.7
    combined.append(Event(at, f"$ {command_label}", CYAN))
    for raw_line in output.splitlines():
        for line in textwrap.wrap(
            _clean(raw_line), width=94, replace_whitespace=False, drop_whitespace=False
        ) or [""]:
            at += 0.08
            combined.append(Event(at, line.rstrip(), WHITE))
    combined.append(Event(at + 0.7, "OKF Markdown is readable and portable.", GREEN))
    return combined


def supplement(run_dir: Path) -> tuple[Path, Path, Path]:
    cast = run_dir / "live-terminal-demo.json"
    bundle = run_dir / "memanto-roundtrip-okf"
    manifest = run_dir / "run-manifest.json"
    if not cast.is_file() or not bundle.is_dir() or not manifest.is_file():
        raise FileNotFoundError(
            "Run directory must contain live-terminal-demo.json, run-manifest.json, "
            "and memanto-roundtrip-okf/"
        )

    before_hash = _sha256(cast)
    command_label = "python show_okf_sample.py ./memanto-roundtrip-okf"
    process = subprocess.run(
        [
            str(resolve_venv_python(ROOT)),
            str(ROOT / "show_okf_sample.py"),
            str(bundle),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if process.returncode:
        raise RuntimeError(process.stdout + process.stderr)

    raw_events = json.loads(cast.read_text(encoding="utf-8"))
    events = [Event(float(item["at"]), str(item["text"]), str(item["color"])) for item in raw_events]
    combined = append_inspection_events(events, process.stdout, command_label=command_label)

    output_cast = run_dir / "live-terminal-demo-with-okf.json"
    output_video = run_dir / "live-terminal-demo-with-okf.mp4"
    provenance = run_dir / "live-terminal-demo-with-okf-provenance.json"
    output_cast.write_text(
        json.dumps(
            [
                {"at": round(event.at, 3), "text": event.text, "color": event.color}
                for event in combined
            ],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    _render(combined, output_video)

    sample_path_line = process.stdout.splitlines()[0]
    relative_sample = sample_path_line.split(":", 1)[1].strip()
    sample = bundle / Path(relative_sample)
    provenance.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source_cast": cast.name,
                "source_cast_sha256": before_hash,
                "source_run_manifest_sha256": _sha256(manifest),
                "command": command_label,
                "command_exit_code": process.returncode,
                "opened_okf_markdown": sample.relative_to(run_dir).as_posix(),
                "opened_okf_markdown_sha256": _sha256(sample),
                "output_cast": output_cast.name,
                "output_cast_sha256": _sha256(output_cast),
                "output_video": output_video.name,
                "output_video_sha256": _sha256(output_video),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output_cast, output_video, provenance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    for path in supplement(args.run_dir.resolve()):
        print(path)


if __name__ == "__main__":
    main()
