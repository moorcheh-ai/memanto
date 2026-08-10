#!/usr/bin/env python3
"""Run the real Hindsight → OKF → Memanto dry-run showcase end to end."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from examples.migrations.hindsight import adapter
    from examples.migrations.hindsight.scenario import (
        DEMO_BANK_ID,
        SESSIONS,
        retain_items,
    )
    from examples.migrations.hindsight.validation import (
        evaluate_retriever,
        hindsight_retriever,
        write_report,
    )
except ModuleNotFoundError:
    # Also support `python run_demo.py` from this directory.
    import adapter  # type: ignore[no-redef]
    from scenario import DEMO_BANK_ID, SESSIONS, retain_items
    from validation import evaluate_retriever, hindsight_retriever, write_report

EXAMPLE_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXAMPLE_DIR.parents[2]
DEFAULT_ARTIFACTS = EXAMPLE_DIR / "artifacts" / "beacon-live-run"


def bypass_proxy_for_local_services() -> None:
    """Keep Hindsight and Ollama loopback traffic out of system proxies."""
    required = {"127.0.0.1", "localhost", "::1"}
    existing = {
        item.strip()
        for key in ("NO_PROXY", "no_proxy")
        for item in os.environ.get(key, "").split(",")
        if item.strip()
    }
    value = ",".join(sorted(existing | required))
    os.environ["NO_PROXY"] = value
    os.environ["no_proxy"] = value


def request_json(
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    method: str | None = None,
) -> Any:
    """Call a local JSON endpoint with a bounded timeout."""
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method=method or ("POST" if body is not None else "GET"),
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.load(response)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise adapter.AdapterError(
            f"Local service request failed for {url}: {exc}"
        ) from exc


def warm_ollama(base_url: str, model: str) -> None:
    """Verify and warm the local model before Hindsight loads its own models."""
    root = base_url.removesuffix("/v1").rstrip("/")
    tags = request_json(f"{root}/api/tags")
    models = {
        item.get("name") for item in tags.get("models", []) if isinstance(item, dict)
    }
    if model not in models:
        raise adapter.AdapterError(
            f"Ollama model {model!r} is not installed. Run: ollama pull {model}"
        )
    result = request_json(
        f"{root}/api/chat",
        {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": "Reply with exactly OK.",
                }
            ],
            "stream": False,
            "think": False,
            "keep_alive": "10m",
            "options": {
                "num_ctx": 8192,
                "num_predict": 8,
                "temperature": 0,
            },
        },
    )
    if not result.get("message", {}).get("content"):
        raise adapter.AdapterError(f"Ollama model {model!r} returned no content")


def model_to_dict(value: Any) -> dict[str, Any]:
    """Convert a generated Hindsight response model to plain JSON data."""
    if hasattr(value, "to_dict"):
        result = value.to_dict()
    elif hasattr(value, "model_dump"):
        result = value.model_dump(mode="json", by_alias=True)
    else:
        result = dict(value)
    if not isinstance(result, dict):
        raise adapter.AdapterError("Hindsight returned a non-object response")
    return result


def populate_bank(client: Any, bank_id: str, *, reset: bool) -> list[dict[str, Any]]:
    """Create the demo bank and retain every evolving source session."""
    if reset:
        try:
            client.banks.delete(bank_id=bank_id)
        except Exception as exc:
            # A missing demo bank is the expected first-run state. Surface
            # authentication, network, and server failures before recreation.
            if getattr(exc, "status", None) != 404:
                raise adapter.AdapterError(
                    f"Could not reset Hindsight bank {bank_id!r}: {exc}"
                ) from exc
    try:
        client.banks.create(
            bank_id=bank_id,
            name="Beacon release copilot",
            mission=(
                "Track the evolving Beacon release plan, retain corrections and "
                "agent experiences, and answer only from recorded evidence."
            ),
        )
    except Exception as exc:
        hint = (
            " Pass --reset-bank to replace this exact demo bank." if not reset else ""
        )
        raise adapter.AdapterError(
            f"Could not create Hindsight bank {bank_id!r}.{hint} {exc}"
        ) from exc

    responses: list[dict[str, Any]] = []
    for index, item in enumerate(retain_items(), 1):
        print(
            f"[retain {index}/{len(SESSIONS)}] {item['document_id']}",
            flush=True,
        )
        try:
            response = client.retain(
                bank_id=bank_id,
                content=item["content"],
                timestamp=item["timestamp"],
                context=item["context"],
                document_id=item["document_id"],
                metadata=item["metadata"],
                tags=item["tags"],
            )
        except Exception as exc:
            raise adapter.AdapterError(
                f"Hindsight retain failed for {item['document_id']}: {exc}"
            ) from exc
        result = model_to_dict(response)
        if not result.get("success"):
            raise adapter.AdapterError(
                f"Hindsight retain failed for {item['document_id']}: {result}"
            )
        responses.append(result)
    return responses


def curate_superseded_facts(
    client: Any,
    *,
    base_url: str,
    bank_id: str,
) -> list[dict[str, Any]]:
    """Invalidate three explicitly superseded facts through Hindsight's API."""
    response = client.memories.list(bank_id=bank_id, limit=100)
    items = model_to_dict(response).get("items", [])
    rules = (
        (
            ("tentative production window", "friday", "july 31"),
            "Superseded by the approved August 4 release window.",
        ),
        (
            ("maya chen", "release dri"),
            "Superseded by the explicit handoff to Luis Ortega.",
        ),
        (
            ("draft runbook incorrectly", "24 hours"),
            "Superseded by the approved six-hour cache TTL.",
        ),
    )
    curated: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for required_phrases, reason in rules:
        matches = [
            item
            for item in items
            if item.get("id") not in used_ids
            and all(
                phrase in str(item.get("text") or "").casefold()
                for phrase in required_phrases
            )
        ]
        if len(matches) != 1:
            raise adapter.AdapterError(
                "Expected one Hindsight fact matching "
                f"{required_phrases}, found {len(matches)}"
            )
        memory_id = str(matches[0]["id"])
        result = request_json(
            adapter.api_memory_url(base_url, bank_id, memory_id),
            {"state": "invalidated", "reason": reason},
            method="PATCH",
        )
        if not isinstance(result, dict) or not result.get("success"):
            raise adapter.AdapterError(
                f"Hindsight invalidate failed for {memory_id}: {result}"
            )
        used_ids.add(memory_id)
        curated.append(
            {
                "id": memory_id,
                "text": matches[0]["text"],
                "reason": reason,
                "response": result,
            }
        )
    return curated


def start_hindsight(
    model: str,
    ollama_url: str,
    timeout: float,
    *,
    port: int,
):
    """Start Hindsight's real embedded API with low-memory local providers."""
    os.environ.setdefault("HINDSIGHT_API_RERANKER_PROVIDER", "rrf")
    os.environ.setdefault("HINDSIGHT_API_LLM_OLLAMA_NUM_CTX", "8192")
    try:
        from hindsight import HindsightClient, HindsightServer
    except ImportError as exc:
        raise adapter.AdapterError(
            "hindsight-all is not installed. Run `uv pip install -r requirements.txt`."
        ) from exc

    server = HindsightServer(
        llm_provider="ollama",
        llm_model=model,
        llm_base_url=ollama_url,
        port=port,
        log_level="warning",
    )
    try:
        server.start(timeout=timeout)
    except Exception as exc:
        server.stop(timeout=10)
        raise adapter.AdapterError(
            f"Hindsight embedded server did not start: {exc}"
        ) from exc
    client = HindsightClient(base_url=server.url, timeout=300)
    return server, client


def run_memanto_dry_run(bundle: Path, artifact_path: Path) -> str:
    """Execute Memanto's shipped OKF importer in no-write mode."""
    executable = REPO_ROOT / ".venv" / "bin" / "memanto"
    if not executable.exists():
        raise adapter.AdapterError(
            f"Memanto development environment not found at {executable}. "
            "Run `uv sync --group dev` from the repository root."
        )
    command = [str(executable), "migrate", "okf", str(bundle), "--dry-run"]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    transcript = f"$ {' '.join(command)}\n\n{result.stdout}" + (
        f"\n[stderr]\n{result.stderr}" if result.stderr else ""
    )
    transcript = transcript.replace(str(REPO_ROOT), "<repo>")
    transcript = transcript.replace(str(Path.home() / ".memanto"), "~/.memanto")
    transcript = "\n".join(line.rstrip() for line in transcript.splitlines())
    transcript = (
        "# Captured from a real dry run; local absolute paths are normalized.\n"
        f"{transcript}"
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(transcript.rstrip() + "\n", encoding="utf-8")
    if result.returncode != 0:
        raise adapter.AdapterError(
            f"`memanto migrate okf --dry-run` failed; see {artifact_path}"
        )
    return transcript


def write_migration_report(
    artifacts: Path,
    manifest: dict[str, Any],
    source_report: dict[str, Any],
) -> None:
    """Write exact counts, sizes, and an honest provider-savings disclosure."""
    bundle = artifacts / "hindsight-okf"
    evidence_dir = artifacts / "evidence"
    source_path = bundle / "source" / "hindsight-memory-snapshot.json"
    bundle_files = [path for path in bundle.rglob("*") if path.is_file()]
    source_bytes = source_path.stat().st_size
    bundle_bytes = sum(path.stat().st_size for path in bundle_files)
    storage_ratio = bundle_bytes / source_bytes if source_bytes else 0.0
    migration = manifest["migration"]
    report = {
        "schema": "hindsight-okf-migration-report/v1",
        "source": {
            "provider": "hindsight",
            "records": migration["source_records"],
            "active_records": migration["importable_records"],
            "archived_records": migration["archived_records"],
            "fact_type_counts": migration["source_fact_type_counts"],
            "snapshot_bytes": source_bytes,
        },
        "okf_input_bundle": {
            "files": len(bundle_files),
            "bytes": bundle_bytes,
            "human_readable": True,
            "snapshot_sha256": manifest["source"]["snapshot_sha256"],
        },
        "dry_run": {
            "okf_nodes": migration["importable_records"],
            "mapped_memories": migration["importable_records"],
            "skipped": 0,
            "type_counts": migration["type_counts"],
        },
        "source_recall": {
            key: source_report[key] for key in ("questions", "passed", "average_score")
        },
        "provider_savings": {
            "available": False,
            "reason": (
                "The shipped OKF importer has no --report option, and the local "
                "Hindsight source has no provider token, latency, or billing "
                "baseline. No synthetic savings are claimed."
            ),
            "storage_delta_bytes": bundle_bytes - source_bytes,
            "storage_ratio": round(storage_ratio, 4),
        },
    }
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "migration-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    type_rows = "\n".join(
        f"| {memory_type.title()} | {count} |"
        for memory_type, count in sorted(migration["type_counts"].items())
    )
    markdown = f"""# Hindsight → OKF migration report

## Actual migration

| Measure | Result |
|---|---:|
| Hindsight source records | {migration["source_records"]} |
| Active records mapped | {migration["importable_records"]} |
| Invalidated records archived | {migration["archived_records"]} |
| Skipped by Memanto dry run | 0 |
{type_rows}
| Source golden-set recall | {source_report["passed"]}/{source_report["questions"]} |

The source snapshot is {source_bytes:,} bytes. The human-readable OKF input
bundle is {bundle_bytes:,} bytes across {len(bundle_files)} files, or
{storage_ratio:.4f}× the snapshot size. The {bundle_bytes - source_bytes:,}-byte
change reflects OKF frontmatter, provenance, indexes, and an audit archive
rather than an attempt to optimize for compact storage.

## Savings disclosure

No provider savings figure is claimed.

The shipped `memanto migrate okf` command deliberately has no `--report`
option, unlike supported-provider migrations. This Path B adapter also uses a
local Hindsight source, so there is no honest provider token, latency, storage,
or billing baseline from which to calculate dollar savings. Inventing one
would be misleading. The exact storage delta above is reported instead.

See `memanto-dry-run.txt` for the captured real CLI output and
`source-recall.json` for every source-side answer and score.
"""
    (evidence_dir / "migration-report.md").write_text(
        markdown,
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    """Create the live-demo argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Run real Hindsight retains and recall, export OKF, then invoke "
            "Memanto's shipped dry-run importer."
        )
    )
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=DEFAULT_ARTIFACTS,
        help=f"Run artifact directory (default: {DEFAULT_ARTIFACTS}).",
    )
    parser.add_argument(
        "--bank-id",
        default=DEMO_BANK_ID,
        help=f"Isolated Hindsight demo bank (default: {DEMO_BANK_ID}).",
    )
    parser.add_argument(
        "--model",
        default="qwen3:4b",
        help="Installed Ollama model used by Hindsight (default: qwen3:4b).",
    )
    parser.add_argument(
        "--ollama-url",
        default="http://127.0.0.1:11434/v1",
        help="Ollama OpenAI-compatible base URL.",
    )
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=300,
        help="Hindsight cold-start timeout in seconds (default: 300).",
    )
    parser.add_argument(
        "--hindsight-port",
        type=int,
        default=8888,
        help="Embedded Hindsight API port (default: 8888).",
    )
    parser.add_argument(
        "--reset-bank",
        action="store_true",
        help="Delete and recreate only the named demo bank before retaining.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing artifact bundle.",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    """Run the showcase and return a process status."""
    args = build_parser().parse_args(argv)
    bypass_proxy_for_local_services()
    artifacts = args.artifacts.expanduser().resolve()
    bundle = artifacts / "hindsight-okf"
    evidence_dir = artifacts / "evidence"
    server = None
    client = None
    try:
        print(f"[1/5] Warming local Ollama model {args.model}", flush=True)
        warm_ollama(args.ollama_url, args.model)
        print("[2/5] Starting embedded Hindsight", flush=True)
        server, client = start_hindsight(
            args.model,
            args.ollama_url,
            args.startup_timeout,
            port=args.hindsight_port,
        )
        print(
            f"[3/5] Retaining {len(SESSIONS)} evolving sessions in bank {args.bank_id}",
            flush=True,
        )
        retain_responses = populate_bank(
            client,
            args.bank_id,
            reset=args.reset_bank,
        )
        curated_facts = curate_superseded_facts(
            client,
            base_url=server.url,
            bank_id=args.bank_id,
        )
        print(
            f"[curation] archived {len(curated_facts)} superseded facts",
            flush=True,
        )
        print("[4/5] Capturing source recall and exporting OKF", flush=True)
        source_report = evaluate_retriever(
            "hindsight",
            hindsight_retriever(client, args.bank_id),
        )
        write_report(source_report, evidence_dir)
        snapshot = adapter.capture_snapshot(
            base_url=server.url,
            bank_id=args.bank_id,
            api_token=None,
            timeout=60,
            include_invalidated=True,
        )
        manifest = adapter.build_bundle(snapshot, bundle, force=args.force)
    except (adapter.AdapterError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        if client is not None:
            client.close()
        if server is not None:
            server.stop(timeout=30)

    try:
        print("[5/5] Running Memanto's no-write OKF import", flush=True)
        run_memanto_dry_run(bundle, evidence_dir / "memanto-dry-run.txt")
        run_summary = {
            "schema": "hindsight-okf-demo-run/v1",
            "source_runtime": {
                "hindsight": "0.8.x",
                "llm_provider": "ollama",
                "llm_model": args.model,
                "bank_id": args.bank_id,
                "retained_sessions": len(retain_responses),
                "curated_invalidations": len(curated_facts),
            },
            "source_validation": {
                key: source_report[key]
                for key in ("questions", "passed", "average_score")
            },
            "migration": manifest["migration"],
            "snapshot_sha256": manifest["source"]["snapshot_sha256"],
            "bundle": "hindsight-okf",
        }
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "run-summary.json").write_text(
            json.dumps(run_summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_migration_report(artifacts, manifest, source_report)
    except (adapter.AdapterError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"Complete: {manifest['migration']['importable_records']} active and "
        f"{manifest['migration']['archived_records']} archived memories.",
        flush=True,
    )
    print(f"Artifacts: {artifacts}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
