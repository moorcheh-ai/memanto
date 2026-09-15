"""Generate sample-okf from fixtures using the shipped CLI."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from grok_to_okf import main

SAMPLE_GENERATED_AT = "2026-09-12T00:51:03Z"

if __name__ == "__main__":
    rc = main(
        [
            "--session",
            str(ROOT / "fixtures" / "mini-session"),
            "--memory",
            str(ROOT / "fixtures" / "MEMORY.md"),
            "--out",
            str(ROOT / "sample-okf"),
            "--generated-at",
            SAMPLE_GENERATED_AT,
        ]
    )
    raise SystemExit(rc)
