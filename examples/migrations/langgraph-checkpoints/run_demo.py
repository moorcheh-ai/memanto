"""Run the reproducible LangGraph checkpoint-to-OKF demonstration."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from generate_demo import generate_database
from langgraph_checkpoint_to_okf import convert_database
from validate_roundtrip import validate

EXAMPLE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EXAMPLE_ROOT.parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate real LangGraph checkpoints and migrate them to OKF."
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        help="new directory for this run (defaults to local-runs/<UTC timestamp>)",
    )
    parser.add_argument(
        "--skip-cli-dry-run",
        action="store_true",
        help="skip the official `memanto migrate okf --dry-run` verification",
    )
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_root = args.output_root or EXAMPLE_ROOT / "local-runs" / stamp
    if output_root.exists():
        raise FileExistsError(
            f"Run directory already exists: {output_root}. Choose a new directory."
        )
    output_root.mkdir(parents=True)

    database = generate_database(output_root / "langgraph-checkpoints.sqlite")
    bundle, checkpoints, records = convert_database(
        database,
        output_root / "okf",
        excluded_channels={"event"},
    )
    parity_report = validate(database, bundle)
    report_path = output_root / "recall-parity.json"
    report_path.write_text(
        json.dumps(parity_report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if not args.skip_cli_dry_run:
        child_env = os.environ.copy()
        import_paths = [str(REPO_ROOT), *(path for path in sys.path if path)]
        if child_env.get("PYTHONPATH"):
            import_paths.append(child_env["PYTHONPATH"])
        child_env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(import_paths))
        subprocess.run(
            [
                sys.executable,
                "-m",
                "memanto.cli.main",
                "migrate",
                "okf",
                str(bundle),
                "--dry-run",
            ],
            cwd=REPO_ROOT,
            env=child_env,
            check=True,
        )

    summary = {
        "source_database": str(database),
        "threads": len(checkpoints),
        "okf_records": len(records),
        "okf_bundle": str(bundle),
        "recall_parity": parity_report["recall_parity"],
        "recall_report": str(report_path),
        "cli_dry_run": not args.skip_cli_dry_run,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
