"""Validate source-to-OKF fidelity using Memanto's shipped loader and mapper."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import yaml  # type: ignore[import-untyped]

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPOSITORY))

from aider_okf import parse_aider_history  # noqa: E402

from memanto.cli.migrate.mappers import map_okf  # noqa: E402
from memanto.cli.migrate.okf_loader import load_okf_bundle  # noqa: E402


def _content_from_body(body: str) -> str:
    lines = body.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    return "\n".join(lines).strip()


def validate(source: Path, bundle: Path, questions: Path) -> dict[str, object]:
    raw = source.read_text(encoding="utf-8")
    source_messages = parse_aider_history(raw)
    export = load_okf_bundle(bundle)
    rows = map_okf(export)

    nodes = export["memories"]
    if len(source_messages) != len(nodes) or len(nodes) != len(rows):
        raise ValueError(
            f"record count mismatch: source={len(source_messages)} "
            f"nodes={len(nodes)} mapped={len(rows)}"
        )

    by_ordinal: dict[int, dict[str, object]] = {}
    for node in nodes:
        metadata = node.get("extra", {}).get("x_aider", {})
        ordinal = int(metadata["ordinal"])
        content = _content_from_body(str(node["body"]))
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if digest != metadata["content_sha256"]:
            raise ValueError(f"content hash mismatch at ordinal {ordinal}")
        by_ordinal[ordinal] = node

    for message in source_messages:
        node = by_ordinal.get(message.ordinal)
        if node is None or _content_from_body(str(node["body"])) != message.content:
            raise ValueError(f"loss detected at ordinal {message.ordinal}")

    golden = yaml.safe_load(questions.read_text(encoding="utf-8"))
    source_text = "\n".join(message.content for message in source_messages)
    mapped_text = "\n".join(str(row["content"]) for row in rows)
    qa_results = []
    for item in golden:
        expected = str(item["expected"])
        source_hit = expected.casefold() in source_text.casefold()
        mapped_hit = expected.casefold() in mapped_text.casefold()
        qa_results.append(
            {
                "question": item["question"],
                "expected": expected,
                "source": source_hit,
                "mapped_okf": mapped_hit,
                "parity": source_hit == mapped_hit and source_hit,
            }
        )

    source_bytes = source.stat().st_size
    okf_bytes = sum(path.stat().st_size for path in bundle.rglob("*") if path.is_file())

    return {
        "source_records": len(source_messages),
        "okf_nodes": len(nodes),
        "mapped_memories": len(rows),
        "skipped": 0,
        "exact_content_hashes": f"{len(nodes)}/{len(nodes)}",
        "golden_recall_parity": f"{sum(bool(item['parity']) for item in qa_results)}/{len(qa_results)}",
        "source_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "storage_evidence": {
            "source_bytes": source_bytes,
            "okf_bundle_bytes": okf_bytes,
            "delta_bytes": okf_bytes - source_bytes,
            "ratio": round(okf_bytes / source_bytes, 3),
            "claim": "OKF expands storage here to preserve readable metadata; no savings claimed.",
        },
        "token_latency_evidence": "Not measured: this offline adapter makes no provider calls.",
        "questions": qa_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("bundle", type=Path)
    parser.add_argument(
        "--questions", type=Path, default=HERE / "golden_questions.yaml"
    )
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    result = validate(args.source, args.bundle, args.questions)
    rendered = yaml.safe_dump(result, sort_keys=False, allow_unicode=True)
    print(rendered.strip())
    if args.receipt:
        args.receipt.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
