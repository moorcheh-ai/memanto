#!/usr/bin/env python3
"""
Standalone showcase runner for the migrations example.

Runs dry-run migrations for chatgpt, claude, gemini, and langgraph
against sample_data/ ZIPs, then prints a per-source summary table.

No live Memanto server or API key is needed when only --dry-run is used.

Usage:
    python migrate.py
    python migrate.py --live --agent my-agent-id
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import zipfile
from pathlib import Path

_HERE = Path(__file__).parent
_SAMPLE = _HERE / "sample_data"
_SCRIPTS = _HERE / "scripts"

# Allow running from repo root or from inside examples/migrations/
_REPO_ROOT = _HERE.parent.parent
for _p in (_HERE, _REPO_ROOT):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)


def _load_runner():
    try:
        from runner import run_migration
        return run_migration
    except ImportError:
        from examples.migrations.runner import run_migration
        return run_migration


def _load_sdk():
    from memanto.cli.client.sdk_client import SdkClient
    return SdkClient


def _parse_zip_export(zip_path: Path, provider: str) -> dict | None:
    import re
    if not zip_path.exists():
        return None
    with zipfile.ZipFile(zip_path) as zf:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp).resolve()
            for member in zf.namelist():
                dest = (tmp_path / member).resolve()
                if not dest.is_relative_to(tmp_path):
                    raise zipfile.BadZipFile(f"Unsafe path in archive: {member}")
            zf.extractall(tmp)

            # Gemini activity JSON format
            json_hits = list(tmp_path.rglob("My Activity.json"))
            if json_hits and provider == "gemini":
                entries = json.loads(json_hits[0].read_text(encoding="utf-8"))
                convs = []
                for e in entries:
                    if not isinstance(e, dict):
                        continue
                    title = (e.get("title") or "").strip()
                    prompt = re.sub(r"^Prompted\s+", "", title).strip()
                    if not prompt:
                        continue
                    convs.append({
                        "messages": [{"role": "user", "text": prompt}],
                        "createdTime": e.get("time"),
                        "id": e.get("gmr_id"),
                    })
                return {"memories": convs}

            json_files = list(tmp_path.rglob("*.json"))
            if not json_files:
                return {"memories": []}

            # chatgpt and claude both use conversations.json
            if provider in ("claude", "chatgpt"):
                conv_file = next((f for f in json_files if f.name == "conversations.json"), None)
                target = conv_file or json_files[0]
            else:
                target = json_files[0]

            data = json.loads(target.read_text(encoding="utf-8"))
            return {"memories": data} if isinstance(data, list) else data


def _print_table(rows: list[tuple]) -> None:
    headers = ["source", "records", "mapped", "skipped", "types", "status"]
    widths = [12, 9, 8, 9, 28, 8]

    def fmt(vals):
        return "  ".join(str(v).ljust(w) for v, w in zip(vals, widths))

    print()
    print(fmt(headers))
    print("-" * (sum(widths) + 2 * (len(widths) - 1)))
    for row in rows:
        print(fmt(row))
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Showcase migration runner")
    parser.add_argument("--agent", default=None, help="Target agent ID (omit for dry-run)")
    parser.add_argument("--live", action="store_true", help="Run live migration (requires --agent and MOORCHEH_API_KEY)")
    args = parser.parse_args()

    dry_run = not args.live
    agent = args.agent

    if args.live and not agent:
        print("--live requires --agent <id>", file=sys.stderr)
        return 1

    run_migration = _load_runner()

    if not dry_run:
        import os
        api_key = os.environ.get("MOORCHEH_API_KEY")
        if not api_key:
            print("MOORCHEH_API_KEY not set", file=sys.stderr)
            return 1
        SdkClient = _load_sdk()
        client = SdkClient(api_key=api_key)
        client.activate_agent(agent, duration_hours=2)
    else:
        client = None

    mode = "dry-run preview" if dry_run else f"live migration → {agent}"
    print(f"\nai-conversations migration showcase  [{mode}]")
    print("=" * 60)

    rows = []
    sources = ["chatgpt", "claude", "gemini"]

    for source in sources:
        print(f"  running {source}...")
        export = _parse_zip_export(_SAMPLE / f"{source}_export.zip", source)
        if export is None:
            rows.append((source, "—", "—", "—", "sample zip missing", "SKIP"))
            continue
        try:
            s, _ = run_migration(
                provider=source,
                export=export,
                client=client,
                agent_id=agent or "",
                dry_run=dry_run,
            )
            types_str = ", ".join(f"{k}:{v}" for k, v in s.type_counts.items()) or "auto"
            rows.append((source, s.source_count, s.mapped_count, s.skipped, types_str, "OK"))
        except Exception as exc:
            rows.append((source, "—", "—", "—", str(exc)[:28], "FAIL"))

    # LangGraph -- use seed file if present
    seed = _SCRIPTS / "langgraph_seed.json"
    if seed.exists():
        print("  running langgraph...")
        try:
            export = json.loads(seed.read_text(encoding="utf-8"))
            s, _ = run_migration(
                provider="langgraph",
                export=export,
                client=client,
                agent_id=agent or "",
                dry_run=dry_run,
            )
            types_str = ", ".join(f"{k}:{v}" for k, v in s.type_counts.items()) or "auto"
            rows.append(("langgraph", s.source_count, s.mapped_count, s.skipped, types_str, "OK"))
        except Exception as exc:
            rows.append(("langgraph", "—", "—", "—", str(exc)[:28], "FAIL"))
    else:
        rows.append(("langgraph", "—", "—", "—", "seed file missing", "SKIP"))

    _print_table(rows)

    if not dry_run and client is not None:
        client.deactivate_agent(agent)

    ok = all(r[5] in ("OK", "SKIP") for r in rows)
    if not ok:
        failed = [r[0] for r in rows if r[5] == "FAIL"]
        print(f"Failed sources: {', '.join(failed)}", file=sys.stderr)
        return 1

    if dry_run:
        print("Dry-run complete. Pass --live --agent <id> to write memories to Memanto.")
    else:
        print("Migration complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
