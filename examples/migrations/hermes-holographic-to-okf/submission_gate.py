#!/usr/bin/env python3
"""Fail closed until the bounty submission has real, complete evidence."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _json(path: Path, blockers: list[str]) -> dict[str, Any]:
    if not path.is_file():
        blockers.append(f"missing evidence file: {path}")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        blockers.append(f"invalid evidence file {path}: {exc}")
        return {}


def _require_fidelity(
    path: Path, blockers: list[str], *, require_memanto_mapping: bool = True
) -> None:
    data = _json(path, blockers)
    if not data:
        return
    if data.get("status") != "PASS" or data.get("mismatches"):
        blockers.append(f"fidelity not clean: {path}")
    mapped = data.get("memanto_loader_mapper") or {}
    if require_memanto_mapping and not mapped.get("checked"):
        blockers.append(f"real Memanto loader/mapper was not checked: {path}")


def evaluate(root: Path, env: dict[str, str] | None = None) -> list[str]:
    env = dict(os.environ if env is None else env)
    reports = root / "reports"
    blockers: list[str] = []

    source = _json(reports / "source-generation.json", blockers)
    if source and not source.get("hermes_commit"):
        blockers.append("source generation is not pinned to a Hermes git commit")
    if source and source.get("sqlite_integrity_check") != "ok":
        blockers.append("source SQLite integrity check is not ok")

    _require_fidelity(reports / "fidelity.json", blockers)
    _require_fidelity(reports / "live-roundtrip-fidelity.json", blockers)
    _require_fidelity(reports / "fresh-destination-fidelity.json", blockers)

    for name in ("primary-golden-recall.txt", "fresh-golden-recall.txt"):
        path = reports / name
        if not path.is_file():
            blockers.append(f"missing golden recall transcript: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if "MISSING EXPECTED TEXT:" in text or "FAIL:" in text:
            blockers.append(f"golden recall transcript contains failures: {path}")

    video = env.get("DEMO_VIDEO_URL", "").strip()
    if not video.startswith(("https://", "http://")):
        blockers.append("DEMO_VIDEO_URL is missing or invalid")

    socials = [
        item.strip()
        for item in env.get("SOCIAL_URLS", "").replace("\n", ",").split(",")
        if item.strip()
    ]
    if not socials or not all(
        url.startswith(("https://", "http://")) for url in socials
    ):
        blockers.append("SOCIAL_URLS must contain at least one valid public post URL")

    if env.get("MEMANTO_ONBOARDING_CONFIRMED") != "1":
        blockers.append("Memanto contributor onboarding is not confirmed")

    return blockers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    blockers = evaluate(args.root)
    if blockers:
        print("NOT READY FOR PR")
        for blocker in blockers:
            print(f"- {blocker}")
        return 1
    print("READY FOR PR")
    print(
        "After opening the PR, complete the BountyHub claim with the PR link before the deadline."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
