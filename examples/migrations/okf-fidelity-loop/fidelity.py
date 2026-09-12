#!/usr/bin/env python3
"""Measure what repeated OKF round trips do to an agent's memory.

Portability only means something if carrying memory out and back is a no-op.
This drives Memanto's shipped OKF code path — ``OkfExportService`` ->
``load_okf_bundle`` -> ``map_okf``, the same path ``memanto migrate okf``
uses — for N generations and reports the drift between them.

    python fidelity.py sample/bundle-gen0 --generations 4

Exits non-zero when the loop never reaches a fixed point.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Any

from memanto.app.services.okf_export_service import OkfExportService
from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle

FOOTER = "[Supporting data]"


def round_trip(bundle: Path, generations: int, workdir: Path) -> list[list[dict]]:
    """Return the mapped rows for the source bundle and each round trip after it."""
    rows = map_okf(load_okf_bundle(bundle))
    history = [rows]
    # exports_dir's parent bounds where write_okf_bundle is allowed to write.
    service = OkfExportService(exports_dir=workdir / "exports")

    for generation in range(1, generations + 1):
        by_type: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            # A foreign entry with no type is auto-classified server-side, which
            # this offline loop cannot do; park it so the bundle stays valid.
            by_type.setdefault(row.get("type") or "context", []).append(row)

        result = service.write_okf_bundle(
            "fidelity",
            by_type,
            output_dir=workdir / f"gen{generation}",
            split="file",
        )
        rows = map_okf(load_okf_bundle(result["output_path"]))
        history.append(rows)

    return history


def measure(rows: list[dict]) -> dict[str, Any]:
    contents = sorted(row["content"] for row in rows)
    return {
        "memories": len(rows),
        "bytes": sum(len(c) for c in contents),
        "footers": sum(c.count(FOOTER) for c in contents),
        "contents": contents,
    }


def report(bundle: Path, history: list[list[dict]]) -> tuple[str, int | None]:
    """Render the drift table and return it with the generation that converged."""
    stats = [measure(rows) for rows in history]
    base = stats[0]["bytes"]
    converged: int | None = None

    lines = [
        "# OKF round-trip fidelity report",
        "",
        f"Source bundle: `{bundle}`",
        "",
        "| Generation | Memories | Content bytes | Footer marks | Drift vs source |",
        "| --- | --- | --- | --- | --- |",
    ]
    for index, stat in enumerate(stats):
        delta = stat["bytes"] - base
        label = "source" if index == 0 else f"round trip {index}"
        lines.append(
            f"| {index} ({label}) | {stat['memories']} | {stat['bytes']:,} "
            f"| {stat['footers']} | {delta:+,} B |"
        )
        if (
            index
            and converged is None
            and stat["contents"] == stats[index - 1]["contents"]
        ):
            converged = index

    lines.append("")
    if converged is None:
        lines.append(
            f"**Not converged** after {len(stats) - 1} round trips — "
            f"content grew {stats[-1]['bytes'] - base:+,} bytes and is still changing."
        )
    else:
        lines.append(
            f"**Converged at generation {converged}** — every later round trip "
            "reproduces it byte for byte."
        )
    return "\n".join(lines) + "\n", converged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="OKF bundle directory to test")
    parser.add_argument(
        "--generations", type=int, default=4, help="round trips to run (default 4)"
    )
    parser.add_argument("--out", type=Path, help="write the report here as well")
    args = parser.parse_args()

    if not args.bundle.exists():
        print(f"OKF bundle not found: {args.bundle}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        history = round_trip(args.bundle, args.generations, Path(tmp))

    text, converged = report(args.bundle, history)
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")

    return 0 if converged is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
