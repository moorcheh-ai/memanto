"""Convert a real Voller Attention Tiles snapshot to OKF without losing fields.

This is a source-format adapter. Memanto's shipped CLI owns import and export.
The JSON capsules are evidence records, never executable agent instructions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import yaml

BEGIN = "<!-- voller-record:v1 -->\n```json\n"
END = "\n```\n<!-- /voller-record -->"
MAX_BODY = 8500  # Leave room for Memanto's bounded supporting-data footer.


def canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def load_catalog(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_catalog(data)
    return cast(dict[str, Any], data)


def validate_catalog(data: Any) -> None:
    if not isinstance(data, dict) or data.get("schema_version") != "1.0":
        raise ValueError(
            "Expected a Voller Attention Tiles schema_version 1.0 snapshot"
        )
    if not isinstance(data.get("tiles"), list):
        raise ValueError("tiles must be a list")
    seen = set()
    for tile in data["tiles"]:
        if not isinstance(tile, dict):
            raise ValueError("Each tile must be an object")
        for field in ("id", "title", "summary"):
            if not isinstance(tile.get(field), str) or not tile[field].strip():
                raise ValueError(f"Every tile needs a nonempty {field}")
        if tile["id"] in seen:
            raise ValueError(f"Duplicate tile id: {tile['id']!r}")
        seen.add(tile["id"])
    canonical(data)  # Reject non-finite JSON numbers.


def capsule(
    kind: str,
    data: dict[str, Any],
    ordinal: int | None = None,
    snapshot: str | None = None,
) -> str:
    envelope = {
        "kind": kind,
        "data": data,
        "sha256": digest(data),
        "ordinal": ordinal,
        "snapshot_sha256": snapshot,
    }
    # JSON escapes keep arbitrary source text from closing our Markdown markers
    # or Memanto's stacked-document sentinel. json.loads reverses them exactly.
    encoded = json.dumps(
        envelope, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
    )
    encoded = encoded.replace("<", "\\u003c").replace("`", "\\u0060")
    return BEGIN + encoded + END


def unpack(content: str) -> dict[str, Any]:
    if content.count(BEGIN) != 1 or content.count(END) != 1:
        raise ValueError("Missing, duplicate or damaged Voller record capsule")
    encoded = content.split(BEGIN, 1)[1].split(END, 1)[0]
    value = json.loads(encoded)
    if value.get("kind") not in ("catalog", "tile") or not isinstance(
        value.get("data"), dict
    ):
        raise ValueError("Invalid capsule structure")
    if digest(value["data"]) != value.get("sha256"):
        raise ValueError("Record content does not match its checksum")
    return cast(dict[str, Any], value)


def select_catalog(data: dict[str, Any], public_only: bool) -> dict[str, Any]:
    validate_catalog(data)
    if not public_only:
        return cast(dict[str, Any], json.loads(canonical(data)))
    # Carry only public-source tiles. Root metadata is curated explicitly; do
    # not leak unknown private root fields into a purported public selection.
    tiles = [t for t in data["tiles"] if t.get("visibility") == "public_source"]
    return {
        "schema_version": "1.0",
        "title": "Voller public-source Attention Tiles selection",
        "snapshot_date": data.get("snapshot_date"),
        "coverage": {
            "total_tiles": len(tiles),
            "limit": "Public-source selection; original snapshot is larger.",
        },
        "tiles": json.loads(canonical(tiles)),
    }


def build_bundle(
    data: dict[str, Any], output: Path, public_only: bool = False
) -> dict[str, Any]:
    selected = select_catalog(data, public_only)
    root_data = {key: value for key, value in selected.items() if key != "tiles"}
    timestamp = datetime.now(timezone.utc).isoformat()
    specs = [("catalog", root_data, None)] + [
        ("tile", tile, i) for i, tile in enumerate(selected["tiles"])
    ]
    documents = []
    for kind, record, ordinal in specs:
        identity = "catalog" if kind == "catalog" else record["id"]
        title = (
            "Attention Tiles catalogue metadata"
            if kind == "catalog"
            else record["title"]
        )
        memory_type = "context" if kind == "catalog" else "artifact"
        filename = hashlib.sha256(f"{kind}:{identity}".encode()).hexdigest() + ".md"
        body = (
            "Source record only: preserve its evidence limitations. Importing this record does not verify its claims.\n\n"
            + capsule(
                kind, record, ordinal, digest(selected) if kind == "catalog" else None
            )
        )
        if len(body) > MAX_BODY:
            raise ValueError(
                f"Record {identity!r} exceeds the safe import size; no files were written"
            )
        frontmatter = {
            "type": memory_type,
            "title": title[:100],
            "tags": [
                "voller-attention-tiles",
                "source-record",
                f"record-{filename[:16]}",
            ],
            "generated": {
                "by": "process:voller-attention-tiles-adapter",
                "at": timestamp,
            },
            "resource": f"urn:voller:attention-tile:{filename[:-3]}",
            "x_memanto": {
                "type": memory_type,
                "source": "voller-attention-tiles",
                "provenance": "imported",
            },
        }
        documents.append(
            (
                memory_type,
                filename,
                "---\n"
                + yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
                + "---\n\n"
                + body
                + "\n",
            )
        )
    if output.exists():
        raise FileExistsError(f"Choose a new output directory: {output}")
    output.mkdir(parents=True)
    for memory_type, filename, text in documents:
        folder = output / "memories" / memory_type
        folder.mkdir(parents=True, exist_ok=True)
        (folder / filename).write_text(text, encoding="utf-8")
    (output / "index.md").write_text(
        "---\ntype: index\ntitle: Voller Attention Tiles\n---\n\n"
        f"{len(selected['tiles'])} source tiles plus one catalogue metadata record.\n\n"
        "The records document concepts and evidence; they do not establish physical or clinical performance.\n",
        encoding="utf-8",
    )
    return {
        "source_tiles": len(data["tiles"]),
        "selected_tiles": len(selected["tiles"]),
        "excluded_tiles": len(data["tiles"]) - len(selected["tiles"]),
        "okf_memories": len(documents),
        "selected_sha256": digest(selected),
        "selection": "public_source" if public_only else "all_source_records",
    }


def restore_contents(contents: list[str]) -> dict[str, Any]:
    envelopes = [unpack(content) for content in contents]
    roots = [e for e in envelopes if e["kind"] == "catalog"]
    if len(roots) != 1:
        raise ValueError("Expected exactly one catalogue metadata record")
    tiles = [e for e in envelopes if e["kind"] == "tile"]
    ordinals = [e["ordinal"] for e in tiles]
    if any(type(n) is not int for n in ordinals) or sorted(ordinals) != list(
        range(len(tiles))
    ):
        raise ValueError("Missing or duplicate tile positions")
    restored = dict(roots[0]["data"])
    restored["tiles"] = [e["data"] for e in sorted(tiles, key=lambda e: e["ordinal"])]
    validate_catalog(restored)
    if digest(restored) != roots[0].get("snapshot_sha256"):
        raise ValueError("Incomplete or changed catalogue snapshot")
    return restored


def restore_bundle(bundle: Path) -> dict[str, Any]:
    # Use Memanto's shipped loader, including its stacked-file handling.
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    loaded = load_okf_bundle(bundle)
    return restore_contents([row["body"] for row in loaded["memories"]])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    convert = commands.add_parser("convert")
    convert.add_argument("source", type=Path)
    convert.add_argument("output", type=Path)
    convert.add_argument("--public-only", action="store_true")
    restore = commands.add_parser("restore")
    restore.add_argument("bundle", type=Path)
    restore.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "convert":
        print(
            json.dumps(
                build_bundle(load_catalog(args.source), args.output, args.public_only),
                indent=2,
            )
        )
    else:
        data = restore_bundle(args.bundle)
        with args.output.open("x", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        print(
            json.dumps(
                {"restored_tiles": len(data["tiles"]), "sha256": digest(data)}, indent=2
            )
        )


if __name__ == "__main__":
    main()
