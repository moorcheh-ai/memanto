"""Export one user's Agno SQLite memories to Memanto-compatible OKF."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def read_memories(
    database: Path, user_id: str, table: str = "agno_memories"
) -> list[dict[str, Any]]:
    """Read a consistent snapshot without opening the source for writes."""
    if not user_id:
        raise ValueError("An explicit, non-empty user ID is required")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise ValueError("Table must be a simple SQLite identifier")
    database = database.resolve(strict=True)
    with closing(
        sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    ) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN")
        records = connection.execute(
            f'SELECT * FROM "{table}" WHERE user_id = ? ORDER BY memory_id',
            (user_id,),
        ).fetchall()
    result = []
    for record in records:
        row = dict(record)
        for field in ("memory", "topics"):
            if row.get(field) is not None:
                row[field] = json.loads(row[field])
        if not isinstance(row.get("memory"), str) or not row["memory"].strip():
            raise ValueError("Expected non-empty string memories from Agno 3.x")
        if not isinstance(row.get("memory_id"), str) or not row["memory_id"]:
            raise ValueError("Every memory needs a stable memory_id")
        topics = row.get("topics")
        if topics is not None and (
            not isinstance(topics, list)
            or not all(isinstance(topic, str) for topic in topics)
        ):
            raise ValueError("Expected topics to be a list of strings or null")
        result.append(row)
    return result


def render(row: dict[str, Any]) -> tuple[str, str]:
    """Keep source metadata in the body: importer extra-field footers are bounded."""
    identity = json.dumps([row["user_id"], row["memory_id"]], ensure_ascii=False)
    digest = hashlib.sha256(identity.encode()).hexdigest()
    metadata = {key: value for key, value in row.items() if key != "memory"}
    body = (
        "## Memory\n\n"
        + row["memory"]
        + "\n\n## Agno source metadata\n\n"
        + json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2)
    )
    if "<!-- okf-entry -->" in body:
        raise ValueError("Source contains Memanto's reserved OKF entry delimiter")
    frontmatter: dict[str, Any] = {
        "type": "context",
        "title": "Agno memory " + digest[:16],
        "tags": row.get("topics") or [],
        "x_memanto": {"source": "agno", "provenance": "imported"},
    }
    for source_key, target_key in (
        ("created_at", "timestamp"),
        ("updated_at", "updated_at"),
    ):
        value = row.get(source_key)
        if value is not None:
            stamp = datetime.fromtimestamp(value, timezone.utc).isoformat()
            if target_key == "timestamp":
                frontmatter[target_key] = stamp
            else:
                frontmatter["x_memanto"][target_key] = stamp
    document = (
        "---\n"
        + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
        + "---\n\n"
        + body
        + "\n"
    )
    return digest + ".md", document


def export(
    database: Path, user_id: str, output: Path, table: str = "agno_memories"
) -> dict:
    """Publish a new bundle only after the actual Memanto mapper preserves each body."""
    from memanto.cli.migrate.mappers import map_okf
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    rows = read_memories(database, user_id, table)
    if not rows:
        raise ValueError("No memories matched; refusing to produce an empty migration")
    output = output.resolve()
    if output.exists():
        raise FileExistsError(
            "Choose a new output directory; existing bundles are preserved"
        )
    rendered = [render(row) for row in rows]
    if len({name for name, _ in rendered}) != len(rows):
        raise ValueError("Duplicate source memory identities")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".agno-export-", dir=output.parent))
    try:
        memories = stage / "memories"
        memories.mkdir()
        for name, document in rendered:
            (memories / name).write_text(document, encoding="utf-8")
        loaded = load_okf_bundle(stage)
        mapped = map_okf(loaded)
        if len(mapped) != len(rows):
            raise ValueError("Memanto changed the memory count")
        for entry, destination in zip(loaded["memories"], mapped, strict=True):
            if not destination["content"].startswith(entry["body"]):
                raise ValueError(
                    "Memanto would truncate a memory. Split it explicitly before migrating."
                )
        summary = {
            "source": "Agno SQLite",
            "records": len(rows),
            "mapped_memories": len(mapped),
            "types": {"context": len(mapped)},
            "body_preserved_by_memanto_mapper": True,
            "live_import_verified": False,
            "savings_report": "Not supplied by memanto migrate okf",
        }
        (stage / "source-records.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (stage / "migration-summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        (stage / "index.md").write_text(
            "---\ntype: index\n---\n\n# Agno memories\n\n"
            + "\n".join(
                f"- [Memory {i + 1}](memories/{name})"
                for i, (name, _) in enumerate(rendered)
            )
            + "\n",
            encoding="utf-8",
        )
        stage.rename(output)
        return summary
    finally:
        # The unique staging bundle is private to this invocation. Its reader
        # lock has been released and can be removed with the staging snapshot.
        (stage.parent / f".{stage.name}.lock").unlink(missing_ok=True)
        if stage.exists():
            if stage.resolve().parent != output.parent or not stage.name.startswith(
                ".agno-export-"
            ):
                raise RuntimeError("Unexpected staging directory; refusing cleanup")
            shutil.rmtree(stage)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--table", default="agno_memories")
    args = parser.parse_args()
    print(
        json.dumps(
            export(args.database, args.user_id, args.output, args.table), indent=2
        )
    )
