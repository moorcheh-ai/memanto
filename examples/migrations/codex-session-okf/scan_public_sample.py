#!/usr/bin/env python3
"""Fail closed when a public demo tree contains redactable values."""

from __future__ import annotations

import argparse
from pathlib import Path

from codex_session_okf.converter import redact_text


def scan_path(root: Path) -> list[str]:
    """Return sanitized findings without echoing the sensitive values."""
    findings: list[str] = []
    paths = (
        [root]
        if root.is_file()
        else sorted(path for path in root.rglob("*") if path.is_file())
    )

    for path in paths:
        relative = path.name if root.is_file() else str(path.relative_to(root))
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(f"{relative}: non-UTF-8 file")
            continue

        _, redaction_count = redact_text(text)
        if redaction_count:
            findings.append(f"{relative}: {redaction_count} sensitive value(s)")

    return findings


def main() -> None:
    """Scan a public sample and fail without printing any matched value."""
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    if not args.path.exists():
        raise SystemExit(f"Public sample path does not exist: {args.path}")

    findings = scan_path(args.path)
    if findings:
        print("Public sample contains sensitive or non-text content:")
        for finding in findings:
            print(f"- {finding}")
        raise SystemExit(1)

    print("Public sample contains no values recognized by the adapter redactor.")


if __name__ == "__main__":
    main()
