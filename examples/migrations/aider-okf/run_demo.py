"""Run the complete offline Aider -> OKF -> Memanto dry-run showcase."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    memanto = shutil.which("memanto")
    if memanto is None:
        raise SystemExit("memanto CLI not found; run this script with `uv run`")

    source = HERE / "data" / "aider.chat.history.md"
    output = Path(tempfile.mkdtemp(prefix="aider-okf-demo-")) / "bundle"
    commands = (
        [sys.executable, str(HERE / "aider_okf.py"), str(source), str(output)],
        [memanto, "migrate", "okf", str(output), "--dry-run"],
        [
            sys.executable,
            str(HERE / "validate.py"),
            str(source),
            str(output),
        ],
    )
    for command in commands:
        print(f"\n$ {' '.join(command)}", flush=True)
        subprocess.run(command, check=True)
    print(f"\nInspectable OKF bundle retained at: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
