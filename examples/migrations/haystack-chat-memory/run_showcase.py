"""Real Haystack source → shipped CLI → optional real Memanto backend → exported OKF."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def main() -> None:
    explicit_api_key = os.environ.get("MOORCHEH_API_KEY")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output", type=Path, help="Fresh evidence directory; never overwrite"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run actual destination import/export and semantic recall",
    )
    parser.add_argument(
        "--agent", help="Fresh dedicated destination agent ID; required for live runs"
    )
    parser.add_argument("--backend", choices=["cloud", "on-prem"], default="cloud")
    parser.add_argument(
        "--server-url",
        default="http://127.0.0.1:18080",
        help="Official on-prem Moorcheh server URL",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Add labeled viewing pauses outside measured CLI durations",
    )
    args = parser.parse_args()
    if args.demo and not args.live:
        parser.error(
            "--demo requires --live so the walkthrough includes a real destination"
        )
    if args.output.exists():
        parser.error("Choose a fresh evidence directory")
    if args.live and (
        not args.agent or (args.backend == "cloud" and not explicit_api_key)
    ):
        parser.error(
            "Live mode needs a fresh --agent; cloud also requires MOORCHEH_API_KEY"
        )
    output = args.output.resolve()
    output.mkdir(parents=True)
    configure_run(output, args.backend, args.server_url)
    with patch.object(Path, "home", return_value=output / "private"):
        execute(args, output, explicit_api_key)


def configure_run(output: Path, backend: str, server_url: str) -> None:
    config = output / "private" / ".memanto"
    config.mkdir(parents=True, mode=0o700)
    (config / "config.yaml").write_text(f"memanto:\n  backend: {backend}\n")
    (config / "config.yaml").chmod(0o600)
    if backend == "on-prem":
        state_dir = config / "on-prem"
        state_dir.mkdir(mode=0o700)
        (state_dir / "state.json").write_text(
            json.dumps(
                {
                    "url": server_url,
                    "embedding_provider": "ollama",
                    "embedding_model": "all-minilm-haystack",
                }
            )
        )


def execute(
    args: argparse.Namespace, output: Path, explicit_api_key: str | None
) -> None:
    from adapter import reconstruct, write_bundle
    from source_history import GOLDEN, SESSION, answer, populate
    from validate import validate

    from memanto.cli.migrate.mappers import map_okf, type_breakdown
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    env = os.environ.copy()
    if explicit_api_key:
        env["MOORCHEH_API_KEY"] = explicit_api_key
    env.update(
        {
            "HAYSTACK_TELEMETRY_ENABLED": "false",
            "HAYSTACK_MEMANTO_CONFIG": str(output / "private"),
            "NO_COLOR": "1",
            "PYTHONUNBUFFERED": "1",
            "MEMANTO_BACKEND": args.backend,
            "MOORCHEH_ONPREM_URL": args.server_url,
            "HAYSTACK_DEMO": "1" if args.demo else "0",
        }
    )
    timings = {}

    def pause(seconds: int) -> None:
        if args.demo:
            print(
                f"[Presentation pause: {seconds}s; excluded from CLI timings]",
                flush=True,
            )
            time.sleep(seconds)

    def cli(*command: str) -> str:
        print("\n$ memanto " + " ".join(command), flush=True)
        started = time.perf_counter()
        process = subprocess.run(
            [sys.executable, str(HERE / "cli.py"), *command],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        elapsed = time.perf_counter() - started
        print(process.stdout, flush=True)
        label = "-".join(command[:2]).replace("/", "_")
        if "--dry-run" in command:
            label += "-dry-run"
        (output / f"cli-{label}.txt").write_text(process.stdout)
        timings[label] = round(elapsed, 3)
        if process.returncode:
            raise RuntimeError(
                f"Shipped CLI failed: {label}; exit {process.returncode}"
            )
        pause(7)
        return process.stdout

    store, snapshot = populate()
    source = snapshot["sessions"][SESSION]
    (output / "source-snapshot.json").write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n"
    )
    print(
        f"Actual Haystack store: {store.count_messages(SESSION)} selected messages, {store.count_messages('other-user')} other-user message excluded.",
        flush=True,
    )
    before = {key: answer(source, key) for key in GOLDEN}
    assert before == GOLDEN
    print(
        "Backend:",
        args.backend,
        "| Actual source API run; no generative model involved.",
        flush=True,
    )
    print("Source golden answers:", json.dumps(before), flush=True)
    pause(8)
    write_bundle(snapshot, SESSION, output / "input-okf")
    cli("migrate", "okf", str(output / "input-okf"), "--dry-run")
    rows = map_okf(load_okf_bundle(output / "input-okf"))
    report = {
        "mode": (
            "LIVE_MEMANTO_ON_PREM"
            if args.backend == "on-prem"
            else "LIVE_MOORCHEH_CLOUD"
        )
        if args.live
        else "LOCAL_SOURCE_AND_CLI_DRY_RUN",
        "backend": args.backend,
        "configured_onprem_embedding": {
            "model": "all-minilm-haystack",
            "base_model": "all-minilm",
            "dimensions": 384,
            "num_ctx": 512,
            "num_batch": 512,
        }
        if args.backend == "on-prem"
        else None,
        "versions": snapshot["versions"],
        "source_messages": len(source),
        "mapped_memories": len(rows),
        "per_type": type_breakdown(rows),
        "source_bytes": (output / "source-snapshot.json").stat().st_size,
        "input_okf_bytes": sum(
            p.stat().st_size for p in (output / "input-okf").rglob("*.md")
        ),
        "savings_report": "Unavailable: shipped migrate okf has no --report option; sizes and wall-clock durations here are independently measured, not token/cost savings.",
    }
    if args.live:
        cli(
            "agent",
            "create",
            args.agent,
            "--description",
            "Isolated Haystack procurement migration showcase",
        )
        cli("migrate", "okf", str(output / "input-okf"), "--agent", args.agent)
        subprocess.run(
            [
                sys.executable,
                str(HERE / "destination_ready.py"),
                args.agent,
                str(len(source)),
            ],
            env=env,
            check=True,
        )
        cli(
            "memory",
            "export",
            "--agent",
            args.agent,
            "--okf",
            "--split",
            "file",
            "--limit",
            str(len(source) + 1),
            "--output",
            "exports/haystack-evidence",
        )
        shutil.copytree(
            output / "private" / ".memanto" / "exports" / "haystack-evidence",
            output / "exported-okf",
        )
        entries = load_okf_bundle(output / "exported-okf")["memories"]
        report["export_validation"] = validate(
            snapshot, SESSION, [entry["body"] for entry in entries]
        )
        print(
            "Actual exported Markdown excerpt (first 18 lines of source position 9):",
            flush=True,
        )
        sample = next(
            entry["body"]
            for entry in entries
            if reconstruct(entry["body"])["position"] == 9
        )
        print("\n".join(sample.splitlines()[:18]), flush=True)
        pause(8)
        # Require exported structured parity before clearing only the demo session.
        store.delete_messages(SESSION)
        assert (
            store.count_messages(SESSION) == 0
            and store.count_messages("other-user") == 1
        )
        print(
            "Source session cleared: 0 messages; unrelated session remains intact.",
            flush=True,
        )
        pause(7)
        report["agent_id"] = args.agent
        subprocess.run(
            [
                sys.executable,
                str(HERE / "destination_recall.py"),
                args.agent,
                str(output / "destination-recall.json"),
            ],
            env=env,
            check=True,
        )
        report["destination_recall"] = json.loads(
            (output / "destination-recall.json").read_text()
        )
        print(
            "Destination export golden answers:",
            json.dumps(
                {
                    key: check["export"]
                    for key, check in report["export_validation"][
                        "golden_checks"
                    ].items()
                }
            ),
            flush=True,
        )
    else:
        report["mapper_validation"] = validate(
            snapshot, SESSION, [row["content"] for row in rows]
        )
    report["presentation_mode"] = args.demo
    report["timing_note"] = (
        "CLI wall-clock durations exclude explicitly labeled presentation pauses"
    )
    report["wall_clock_seconds"] = timings
    report["source_sha256"] = hashlib.sha256(
        (output / "source-snapshot.json").read_bytes()
    ).hexdigest()
    (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    if args.demo:
        print(
            "Verified result:",
            report["source_messages"],
            "source messages and",
            report["export_validation"]["reconstructed_messages"],
            "unchanged exported messages; four real recall answers passed.",
            flush=True,
        )
        print(
            "Measured CLI seconds (presentation pauses excluded):",
            json.dumps(timings),
            flush=True,
        )
        print("Full measured report:", output / "summary.json", flush=True)
    else:
        print(json.dumps(report, indent=2), flush=True)
    print(
        "No cloud import or cloud export happened."
        if not args.live
        else "Destination import/export and exact source reconstruction succeeded. Four real semantic recall queries also passed.",
        flush=True,
    )

    pause(8)


if __name__ == "__main__":
    main()
