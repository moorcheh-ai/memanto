"""Run the checked-in real-vault migration and deterministic fidelity gate."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from obsidian_to_okf import convert_vault  # noqa: E402

from memanto.cli.migrate.mappers import map_okf  # noqa: E402
from memanto.cli.migrate.okf_loader import load_okf_bundle  # noqa: E402

GOLDEN_QUERIES = {
    "Who is the protagonist?": ("Mara Vance", "protagonist"),
    "What system governs lamplight memory?": ("Lamplight Memory", "soft magic"),
    "What is the Bureau trying to keep forgotten?": (
        "Bureau of Continuance",
        "shared forgetting",
    ),
}


def _score(rows: list[dict[str, object]]) -> dict[str, bool]:
    corpus = {
        str(row.get("title")): str(row.get("content", "")).casefold() for row in rows
    }
    return {
        question: expected.casefold() in corpus.get(title, "")
        for question, (title, expected) in GOLDEN_QUERIES.items()
    }


def main() -> None:
    source = ROOT / "sample-source-vault"
    output = ROOT / "sample-okf"
    report = convert_vault(source, output)
    loaded = load_okf_bundle(output)
    mapped = map_okf(loaded)
    golden = _score(mapped)
    receipt = {
        "source": "leethobbit/obsidian-inkswell-plugin sample vault",
        "source_records": report.source_files,
        "okf_records": len(loaded["memories"]),
        "mapped_memories": len(mapped),
        "source_sha256": report.source_sha256,
        "type_counts": report.type_counts,
        "resolvable_wikilinks_converted": report.wikilinks_converted,
        "unresolved_wikilinks_preserved": len(report.unresolved_links),
        "golden_recall": golden,
        "golden_recall_score": f"{sum(golden.values())}/{len(golden)}",
        "is_lossless_by_record_count": (
            report.source_files == len(loaded["memories"]) == len(mapped)
        ),
    }
    (output / "validation-report.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"migration": asdict(report), "validation": receipt}, indent=2))
    if not receipt["is_lossless_by_record_count"] or not all(golden.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
