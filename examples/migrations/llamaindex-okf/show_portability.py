"""Show the lock-in problem and the portable OKF recovery without a paid model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from migrate_to_okf import _text_from_message, load_rows
from validate_round_trip import okf_records


def source_corpus(database: Path) -> str:
    return "\n".join(
        _text_from_message(json.loads(row["data"])) for row in load_rows(database)
    )


def portable_corpus(bundle: Path) -> str:
    return "\n".join(record["text"] for record in okf_records(bundle).values())


def score(corpus: str, golden_path: Path) -> dict:
    lowered = corpus.lower()
    cases = json.loads(golden_path.read_text(encoding="utf-8"))
    results = [
        {
            "question": case["question"],
            "answer": case["expected"] if case["expected"].lower() in lowered else None,
            "passed": case["expected"].lower() in lowered,
        }
        for case in cases
    ]
    return {
        "answered": sum(item["passed"] for item in results),
        "total": len(results),
        "results": results,
    }


def portability_story(database: Path, bundle: Path, golden_path: Path) -> dict:
    source = score(source_corpus(database), golden_path)
    switched_without_export = score("", golden_path)
    recovered_from_okf = score(portable_corpus(bundle), golden_path)
    return {
        "before_switch_llamaindex": source,
        "after_switch_without_export": switched_without_export,
        "after_open_okf": recovered_from_okf,
        "passed": (
            source["answered"] == source["total"]
            and switched_without_export["answered"] == 0
            and recovered_from_okf["answered"] == recovered_from_okf["total"]
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("bundle", type=Path)
    parser.add_argument(
        "--golden", type=Path, default=Path(__file__).with_name("golden_qa.json")
    )
    args = parser.parse_args()
    story = portability_story(args.database, args.bundle, args.golden)
    print(json.dumps(story, indent=2, ensure_ascii=False))
    if not story["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
