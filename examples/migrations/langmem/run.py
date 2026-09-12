"""Run a local LangMem indexed-store export into Memanto's OKF writer."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from fastembed import TextEmbedding
from langgraph.store.base import IndexConfig
from langgraph.store.memory import InMemoryStore
from langmem import create_manage_memory_tool

from memanto.app.services.okf_export_service import OkfExportService

HERE = Path(__file__).resolve().parent
MARKER = "[LangMem source record base64]"


def canonical(value: Any) -> str:
    """Serialize exact JSON data, refusing non-finite numbers."""
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    if json.loads(encoded) != value:
        raise ValueError("source contains values that change under JSON serialization")
    return encoded


def identity(record: dict[str, Any]) -> str:
    """Distinguish namespace components without delimiter collisions."""
    return canonical([record["namespace"], record["key"]])


def validate_export(export: Any) -> list[dict[str, Any]]:
    """Validate the public export shape before creating any output."""
    if not isinstance(export, dict) or not isinstance(export.get("memories"), list):
        raise ValueError("export must contain a memories array")
    seen = set()
    for record in export["memories"]:
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("namespace"), list)
            or not record["namespace"]
            or not all(isinstance(part, str) and part for part in record["namespace"])
            or not isinstance(record.get("key"), str)
            or not record["key"]
            or not isinstance(record.get("value"), dict)
        ):
            raise ValueError(
                "record requires namespace:list[str], key:str, value:object"
            )
        canonical(record)
        key = identity(record)
        if key in seen:
            raise ValueError("duplicate namespace/key identity")
        seen.add(key)
    if "count" in export and (
        type(export["count"]) is not int or export["count"] != len(export["memories"])
    ):
        raise ValueError("export count does not match memories array")
    return list(export["memories"])


def decode_snapshots(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recover exact records from imported content, rejecting missing data."""
    records = []
    pattern = re.compile(r"^" + re.escape(MARKER) + r"\n([A-Za-z0-9+/=]+)$", re.M)
    for row in rows:
        matches = pattern.findall(row["content"])
        if len(matches) != 1:
            raise ValueError("expected exactly one complete source snapshot")
        record = json.loads(base64.b64decode(matches[0], validate=True))
        records.append(record)
    validate_export({"memories": records})
    return records


def build_source() -> tuple[InMemoryStore, list[tuple[str, ...]]]:
    model = TextEmbedding("BAAI/bge-small-en-v1.5")

    def embed(texts: Sequence[str]) -> list[list[float]]:
        return [v.tolist() for v in model.embed(texts)]

    index: IndexConfig = {"dims": model.embedding_size, "embed": embed}
    store = InMemoryStore(index=index)
    scopes: list[tuple[str, ...]] = [
        ("memories", "synthetic-user"),
        ("memories", "synthetic-team"),
    ]
    operations = [
        (scopes[0], "pref", "User prefers Python for backend work."),
        (scopes[0], "city", "User lives in Delhi and enjoys masala tea."),
        (scopes[0], "framework", "User is building a mobile app with React Native."),
        (scopes[1], "policy", "Team requires UTF-8 JSONL exports."),
        (scopes[1], "owner", "Team's release owner is Priya."),
    ]
    for namespace, key, content in operations:
        tool = create_manage_memory_tool(namespace=namespace, store=store)
        result = tool.invoke({"content": content, "action": "create"})
        source_id = result.rsplit(" ", 1)[-1]
        if key == "owner":
            tool.invoke(
                {
                    "content": "Team's release owner is Priya N.",
                    "action": "update",
                    "id": source_id,
                }
            )
        if key == "policy":
            tool.invoke({"content": None, "action": "delete", "id": source_id})
    return store, scopes


def export_records(
    store: InMemoryStore, scopes: list[tuple[str, ...]]
) -> dict[str, Any]:
    records = []
    seen: set[tuple[tuple[str, ...], str]] = set()
    for namespace in scopes:
        offset = 0
        while True:
            page = store.search(namespace, offset=offset, limit=100)
            if not page:
                break
            for item in page:
                identity = (tuple(item.namespace), str(item.key))
                if identity in seen:
                    continue
                seen.add(identity)
                records.append(
                    {
                        "namespace": list(item.namespace),
                        "key": str(item.key),
                        "value": item.value,
                        "created_at": item.created_at.isoformat()
                        if item.created_at
                        else None,
                        "updated_at": item.updated_at.isoformat()
                        if item.updated_at
                        else None,
                    }
                )
            offset += len(page)
    records.sort(key=lambda r: (r["namespace"], r["key"]))
    return {"source": "langmem", "memories": records, "count": len(records)}


def to_okf(export: dict[str, Any], output: Path) -> dict[str, Any]:
    records = validate_export(export)
    groups: dict[str, list[dict[str, Any]]] = {
        "fact": [],
        "preference": [],
        "context": [],
    }
    for record in sorted(records, key=identity):
        raw_content = record["value"].get("content", record["value"])
        content = (
            raw_content if isinstance(raw_content, str) else canonical(raw_content)
        )
        source_id = hashlib.sha256(identity(record).encode("utf-8")).hexdigest()
        mem_type = (
            "preference"
            if any(w in content.lower() for w in ("prefer", "likes", "requires"))
            else "fact"
        )
        snapshot = base64.b64encode(
            json.dumps(
                record, ensure_ascii=False, sort_keys=True, allow_nan=False
            ).encode()
        ).decode()
        # The shipped loader uses this marker to split stacked files. Escape
        # it in the human body; the source snapshot below remains exact.
        safe_content = content.replace(
            MARKER, "[LangMem source marker (escaped)]"
        ).replace("<!-- okf-entry -->", "<!-- okf-entry (escaped) -->")
        body = f"{safe_content}\n\n[LangMem source record base64]\n{snapshot}"
        if len(body) > 8500:
            raise ValueError(
                f"record {record['key']} exceeds safe OKF size; refusing truncation"
            )
        groups[mem_type].append(
            {
                "title": safe_content[:80],
                "content": body,
                "tags": ["langmem"],
                "source": "langmem",
                "source_ref": f"langmem://store/{source_id}",
                "provenance": "imported",
                "created_at": record.get("created_at"),
                "updated_at": record.get("updated_at"),
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    service = OkfExportService(exports_dir=output.parent)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    result = service.write_okf_bundle(
        agent_id="langmem-local",
        memories_by_type=groups,
        output_dir=output,
        split="file",
    )
    from memanto.cli.migrate.mappers import map_okf
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    loaded = map_okf(load_okf_bundle(output))
    if len(loaded) != len(records):
        raise RuntimeError(
            f"OKF conservation failed: {len(loaded)} of {len(records)} records loaded"
        )
    decoded = decode_snapshots(loaded)
    if canonical(sorted(decoded, key=identity)) != canonical(
        sorted(records, key=identity)
    ):
        raise RuntimeError(
            "OKF conservation failed: source snapshots or identities changed"
        )
    return {
        "source_count": len(records),
        "mapped_count": sum(map(len, groups.values())),
        "bundle": str(output),
        "sections": result["sections"],
        "per_type": {key: len(value) for key, value in groups.items() if value},
        "conserved_records": len(decoded),
        "source_bytes": len(json.dumps(export, ensure_ascii=False).encode()),
        "bundle_bytes": sum(p.stat().st_size for p in output.rglob("*") if p.is_file()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=HERE / "artifacts" / "sample-run",
        help="New run directory; existing output is never overwritten",
    )
    parser.add_argument(
        "--source-export", type=Path, help="Existing LangMem JSON export"
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError("run directory exists; choose a new --output")
    store = None
    scopes: list[tuple[str, ...]] = []
    if args.source_export:
        export = json.loads(args.source_export.read_text(encoding="utf-8"))
    else:
        store, scopes = build_source()
        export = export_records(store, scopes)
    validate_export(export)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".langmem-run-", dir=output.parent) as tmp:
        staging = Path(tmp)
        summary = to_okf(export, staging / "okf-bundle")
        report: dict[str, Any] = {
            "summary": summary,
            "source_retrieval": [],
            "target_recall": "not run",
            "cost_savings": None,
            "latency_savings": None,
            "source_note": "synthetic scenario through real tools"
            if store
            else "provided export; source retrieval not run",
        }
        if store is not None:
            for query, expected in (
                ("server-side programming language", "Python"),
                ("city and drink", "Delhi"),
                ("mobile framework", "React Native"),
                ("unrelated quantum physics", None),
            ):
                hits = store.search(scopes[0], query=query, limit=1)
                top = hits[0] if hits else None
                report["source_retrieval"].append(
                    {
                        "query": query,
                        "expected_phrase": expected,
                        "score": top.score if top else None,
                        "top1": top.value if top else None,
                        "positive_top1_match": expected in canonical(top.value)
                        if top and expected
                        else None,
                        "negative_control": expected is None,
                    }
                )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "memanto",
                "migrate",
                "okf",
                "okf-bundle",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=staging,
        )
        cli_output = result.stdout.replace(str(staging), "<run>").replace(
            str(Path.home()), "~"
        )
        cli_output = "\n".join(line.rstrip() for line in cli_output.splitlines()) + "\n"
        (staging / "cli-dry-run.txt").write_text(cli_output, encoding="utf-8")
        for metric in (staging / "okf-bundle" / "metrics").rglob("*.md"):
            normalized = (
                "\n".join(
                    line.rstrip()
                    for line in metric.read_text(encoding="utf-8").splitlines()
                ).rstrip()
                + "\n"
            )
            metric.write_text(normalized, encoding="utf-8")
        (staging / ".okf-bundle.lock").unlink(missing_ok=True)
        (staging / "langmem_export.json").write_text(
            canonical(export), encoding="utf-8"
        )
        summary["bundle"] = "okf-bundle"
        summary["source_bytes"] = (staging / "langmem_export.json").stat().st_size
        summary["bundle_bytes"] = sum(
            p.stat().st_size for p in (staging / "okf-bundle").rglob("*") if p.is_file()
        )
        (staging / "run-report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        if output.exists():
            raise FileExistsError(
                "run directory appeared while generating; refusing overwrite"
            )
        os.rename(staging, output)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
