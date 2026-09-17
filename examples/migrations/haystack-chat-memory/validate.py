"""Validate an actual Memanto exported OKF bundle against the source snapshot."""

import argparse
import json
from pathlib import Path

from adapter import load_snapshot, reconstruct
from source_history import GOLDEN, answer

from memanto.cli.migrate.okf_loader import load_okf_bundle


def validate(snapshot: dict, session: str, contents: list[str]) -> dict:
    recovered = [reconstruct(content) for content in contents]
    if any(item["session_id"] != session for item in recovered):
        raise ValueError("Unexpected session in the destination export")
    recovered.sort(key=lambda item: item["position"])
    messages = [item["message"] for item in recovered]
    expected = snapshot["sessions"][session]
    if [item["position"] for item in recovered] != list(range(len(expected))):
        raise ValueError("Missing or duplicated source positions")
    if messages != expected:
        raise ValueError("Source messages changed across the round trip")
    checks = {
        key: {
            "source": answer(expected, key),
            "export": answer(messages, key),
            "expected": value,
        }
        for key, value in GOLDEN.items()
    }
    if any(
        check["source"] != check["expected"] or check["export"] != check["expected"]
        for check in checks.values()
    ):
        raise ValueError("Golden answer mismatch")
    return {
        "source_messages": len(expected),
        "reconstructed_messages": len(messages),
        "exact_structured_parity": True,
        "golden_checks": checks,
        "recall_method": "deterministic latest-setting agent over complete source/export history; not a hosted semantic recall query",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--session", required=True)
    args = parser.parse_args()
    entries = load_okf_bundle(args.bundle)["memories"]
    print(
        json.dumps(
            validate(
                load_snapshot(args.snapshot),
                args.session,
                [item["body"] for item in entries],
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
