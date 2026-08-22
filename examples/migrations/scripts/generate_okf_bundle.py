#!/usr/bin/env python3
"""
Generate the sample OKF bundle from local sample data.

This script is the only correct way to update okf_bundle/. Never edit that
directory by hand.

What it does:
  1. Maps each sample source (LangGraph seed + conversation ZIPs) through the
     example mappers — no live Memanto agent or API key required.
  2. Assigns a fallback type of "context" to any row left as type=None (these
     would normally be auto-classified by the Memanto parsing service on a
     real import).
  3. Writes the full OKF bundle to okf_bundle/ via OkfExportService, which
     owns the on-disk format.

Usage:
    python scripts/generate_okf_bundle.py
    python scripts/generate_okf_bundle.py --out /tmp/preview_bundle
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import zipfile
from pathlib import Path

_HERE = Path(__file__).parent
_MIGRATIONS = _HERE.parent
_SAMPLE = _MIGRATIONS / "sample_data"
_REPO_ROOT = _MIGRATIONS.parent.parent

for _p in (_MIGRATIONS, _REPO_ROOT):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from mappers import map_chatgpt, map_claude, map_gemini, map_langgraph  # type: ignore[import]
from memanto.app.services.okf_export_service import OkfExportService

_AGENT_ID = "ai-conversations-showcase"
_FALLBACK_TYPE = "context"


def _load_zip_export(zip_path: Path, provider: str) -> dict:
    import re

    if not zip_path.exists():
        return {"memories": []}

    with zipfile.ZipFile(zip_path) as zf:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp).resolve()
            for member in zf.namelist():
                dest = (tmp_path / member).resolve()
                if not dest.is_relative_to(tmp_path):
                    raise zipfile.BadZipFile(f"Unsafe path in archive: {member}")
            zf.extractall(tmp)

            if provider == "gemini":
                json_hits = list(tmp_path.rglob("My Activity.json"))
                if json_hits:
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

            conv_file = next((f for f in json_files if f.name == "conversations.json"), None)
            target = conv_file or json_files[0]
            data = json.loads(target.read_text(encoding="utf-8"))
            return {"memories": data} if isinstance(data, list) else data


async def _build_langgraph_export() -> dict:
    try:
        from langgraph.store.memory import InMemoryStore

        store = InMemoryStore()
        await store.aput(("user", "alice", "memories"), "pref-editor", {"content": "Alice uses VSCode with dark mode as her primary editor."})
        await store.aput(("user", "alice", "memories"), "pref-lang", {"content": "Alice prefers Python and FastAPI over JavaScript."})
        await store.aput(("user", "alice", "facts"), "location", {"content": "Alice is based in Berlin, Germany."})
        await store.aput(("project", "example-project"), "goal-1", {"content": "Build an open-source agentic memory layer.", "priority": "high"})

        items = []
        seen: set[tuple] = set()
        for ns in await store.alist_namespaces():
            offset = 0
            limit = 1000
            while True:
                try:
                    batch = await store.asearch(ns, limit=limit, offset=offset)
                except TypeError:
                    batch = await store.asearch(ns)
                    for item in batch:
                        key = (tuple(item.namespace), item.key)
                        if key not in seen:
                            seen.add(key)
                            items.append({
                                "namespace": list(item.namespace),
                                "key": item.key,
                                "value": item.value,
                                "created_at": item.created_at.isoformat() if item.created_at else None,
                            })
                    break
                if not batch:
                    break
                for item in batch:
                    key = (tuple(item.namespace), item.key)
                    if key not in seen:
                        seen.add(key)
                        items.append({
                            "namespace": list(item.namespace),
                            "key": item.key,
                            "value": item.value,
                            "created_at": item.created_at.isoformat() if item.created_at else None,
                        })
                if len(batch) < limit:
                    break
                offset += limit
        return {"items": items}
    except ImportError:
        print("  [skip] langgraph not installed — omitting LangGraph memories", file=sys.stderr)
        return {"items": []}


def _collect_rows() -> list[dict]:
    rows: list[dict] = []

    print("  mapping chatgpt...")
    rows += map_chatgpt(_load_zip_export(_SAMPLE / "chatgpt_export.zip", "chatgpt"))

    print("  mapping claude...")
    rows += map_claude(_load_zip_export(_SAMPLE / "claude_export.zip", "claude"))

    print("  mapping gemini...")
    rows += map_gemini(_load_zip_export(_SAMPLE / "gemini_export.zip", "gemini"))

    print("  mapping langgraph...")
    lg_export = asyncio.run(_build_langgraph_export())
    rows += map_langgraph(lg_export)

    return rows


def _apply_fallback_type(rows: list[dict]) -> list[dict]:
    for row in rows:
        if row.get("type"):
            continue
        source = row.get("source", "")
        content = (row.get("content") or "").lower()
        tags = " ".join(row.get("tags") or []).lower()

        if source == "langgraph":
            if "goal" in tags or "goal" in content[:80]:
                row["type"] = "goal"
            elif "pref" in tags or "prefer" in content[:80]:
                row["type"] = "preference"
            elif "fact" in tags or "location" in tags:
                row["type"] = "fact"
            else:
                row["type"] = "context"
        else:
            row["type"] = "context"

    return rows


def _group_by_type(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        t = row.get("type") or _FALLBACK_TYPE
        grouped.setdefault(t, []).append(row)
    return grouped


def _clean_bundle(out_dir: Path) -> None:
    import shutil

    if not out_dir.exists():
        return

    expected_markers = {"memories", "metrics", "index.md"}
    existing = {child.name for child in out_dir.iterdir()}
    is_empty = len(existing) == 0
    has_bundle_markers = bool(existing & expected_markers)

    if not is_empty and not has_bundle_markers:
        raise RuntimeError(
            f"Refusing to delete {out_dir}: directory exists but does not look like a "
            "previously generated OKF bundle. Remove it manually if you are sure."
        )

    for child in out_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate the sample OKF bundle")
    parser.add_argument(
        "--out",
        type=Path,
        default=_MIGRATIONS / "okf_bundle",
        help="Output directory (default: examples/migrations/okf_bundle)",
    )
    args = parser.parse_args()

    out_dir: Path = args.out.resolve()
    print(f"\ngenerating OKF bundle  ->  {out_dir}")
    print("=" * 60)

    try:
        _clean_bundle(out_dir)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    rows = _collect_rows()
    if not rows:
        print("no rows mapped — nothing to write", file=sys.stderr)
        return 1

    rows = _apply_fallback_type(rows)
    by_type = _group_by_type(rows)

    type_summary = ", ".join(f"{t}:{len(v)}" for t, v in sorted(by_type.items()))
    print(f"  {len(rows)} memories across {len(by_type)} types: {type_summary}")

    svc = OkfExportService(exports_dir=out_dir.parent)
    result = svc.write_okf_bundle(
        agent_id=_AGENT_ID,
        memories_by_type=by_type,
        output_dir=out_dir,
    )

    print(f"\nbundle written: {result['output_path']}")
    print(f"total memories: {result['total_memories']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
