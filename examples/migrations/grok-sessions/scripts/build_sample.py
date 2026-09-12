"""Generate sample-okf from fixtures using the shipped CLI."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from grok_to_okf import main

if __name__ == "__main__":
    rc = main(
        [
            "--session",
            str(ROOT / "fixtures" / "mini-session"),
            "--memory",
            str(ROOT / "fixtures" / "MEMORY.md"),
            "--out",
            str(ROOT / "sample-okf"),
        ]
    )
    raise SystemExit(rc)
