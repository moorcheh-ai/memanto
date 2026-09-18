#!/usr/bin/env python3
"""One-command Path C showcase: multi-source lock-in → consolidated OKF wiki.

Pipeline:
  1. Seed a real Chroma PersistentClient (vector-trapped agent memory)
  2. Seed a real proprietary SQLite agent_memories store
  3. Adapt both sources into typed memory dicts
  4. Consolidate (dedupe + resolve contradictions)
  5. Write a portable OKF v0.2 bundle
  6. Score golden Q&A recall parity
  7. Optionally invoke ``memanto migrate okf ... --dry-run``
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from adapters import load_chroma_memories, load_sqlite_memories
from consolidate import archive_session_notes, consolidate
from okf_writer import write_okf_bundle
from seed_chroma import seed_chroma
from seed_sqlite_store import seed_sqlite
from validate import evaluate_parity, render_markdown

ROOT = Path(__file__).resolve().parent


def _copy_sample(bundle: Path, summary: dict, parity: dict, reports_dir: Path) -> None:
    sample = ROOT / "sample"
    if sample.exists():
        shutil.rmtree(sample)
    shutil.copytree(bundle, sample / "okf-bundle")
    (sample / "migration_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (sample / "recall-parity.json").write_text(
        json.dumps(parity, indent=2) + "\n", encoding="utf-8"
    )
    (sample / "recall-parity.md").write_text(render_markdown(parity), encoding="utf-8")
    for name in ("chroma_seed.json", "sqlite_seed.json", "memanto-dry-run.txt"):
        src = reports_dir / name
        if src.exists():
            shutil.copy2(src, sample / name)


def _try_memanto_dry_run(bundle: Path, out_txt: Path) -> str | None:
    cmd = ["memanto", "migrate", "okf", str(bundle), "--dry-run"]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            cwd=str(ROOT.parents[2]),  # repo root
        )
    except FileNotFoundError:
        # Fall back to `python -m memanto` if the console script is missing.
        cmd = [
            sys.executable,
            "-m",
            "memanto",
            "migrate",
            "okf",
            str(bundle),
            "--dry-run",
        ]
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                cwd=str(ROOT.parents[2]),
            )
        except FileNotFoundError:
            return None

    text = (proc.stdout or "") + (proc.stderr or "")
    out_txt.write_text(text, encoding="utf-8")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild source stores and wipe out/",
    )
    parser.add_argument(
        "--skip-memanto",
        action="store_true",
        help="Skip the optional memanto migrate okf --dry-run step",
    )
    parser.add_argument(
        "--update-sample",
        action="store_true",
        help="Refresh the committed sample/ artifacts from this run",
    )
    args = parser.parse_args()

    out = ROOT / "out"
    data = ROOT / "data"
    if args.force and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    chroma_dir = data / "chroma"
    sqlite_path = data / "sqlite" / "agent_memory.db"

    print("==> Seeding Chroma PersistentClient (real vector store)")
    chroma_report = seed_chroma(chroma_dir, force=args.force)
    (out / "chroma_seed.json").write_text(
        json.dumps(chroma_report, indent=2) + "\n", encoding="utf-8"
    )
    print(f"    {chroma_report['count']} points in {chroma_report['collection']}")

    print("==> Seeding proprietary SQLite agent_memories store")
    sqlite_report = seed_sqlite(sqlite_path, force=args.force)
    (out / "sqlite_seed.json").write_text(
        json.dumps(sqlite_report, indent=2) + "\n", encoding="utf-8"
    )
    print(f"    {sqlite_report['count']} rows in {sqlite_report['table']}")

    print("==> Adapting sources")
    chroma_memories = load_chroma_memories(chroma_dir)
    sqlite_memories = load_sqlite_memories(sqlite_path)
    print(f"    chroma={len(chroma_memories)} sqlite={len(sqlite_memories)}")

    print("==> Consolidating (dedupe + contradiction resolution)")
    active, archived, summary = consolidate(chroma_memories, sqlite_memories)
    print(
        f"    active={summary['active_count']} archived={summary['archived_count']} "
        f"types={summary['per_type']}"
    )

    # Also write per-source OKF bundles so reviewers can inspect each hop.
    from okf_writer import write_okf_bundle as _write

    _write(chroma_memories, out / "okf-chroma-only", agent_id="chroma-source")
    _write(sqlite_memories, out / "okf-sqlite-only", agent_id="sqlite-source")

    print("==> Writing consolidated OKF v0.2 bundle")
    bundle = out / "okf-bundle"
    okf_summary = write_okf_bundle(
        active,
        bundle,
        agent_id="priya-coding-assistant",
        session_notes=archive_session_notes(archived),
    )
    summary["okf"] = okf_summary
    (out / "migration_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(f"    {okf_summary['total_memories']} markdown memories → {bundle}")

    print("==> Golden Q&A recall parity")
    # Source corpus = pre-consolidation union (what the agent knew across tools)
    # OKF corpus = consolidated portable wiki (what you own after escape)
    union = chroma_memories + sqlite_memories
    parity = evaluate_parity(
        source_memories=active,  # after consolidation, before/after should match
        okf_bundle=bundle,
        questions_path=ROOT / "golden_questions.json",
    )
    # Also prove the union could answer the same questions pre-consolidation.
    pre = evaluate_parity(
        source_memories=union,
        okf_bundle=bundle,
        questions_path=ROOT / "golden_questions.json",
    )
    parity["pre_consolidation_union_recall"] = pre["source_recall"]
    (out / "recall-parity.json").write_text(
        json.dumps(parity, indent=2) + "\n", encoding="utf-8"
    )
    (out / "recall-parity.md").write_text(render_markdown(parity), encoding="utf-8")
    print(
        f"    source {parity['source_recall']} | okf {parity['okf_recall']} | "
        f"preserved={parity['is_recall_preserved']}"
    )

    dry_run_text = None
    if not args.skip_memanto:
        print("==> memanto migrate okf --dry-run (shipped CLI)")
        dry_run_text = _try_memanto_dry_run(bundle, out / "memanto-dry-run.txt")
        if dry_run_text is None:
            print(
                "    (memanto CLI not installed — skipped; pip install -e . from repo root)"
            )
        else:
            # Print a short excerpt for the terminal demo.
            excerpt = "\n".join(dry_run_text.strip().splitlines()[-20:])
            print(excerpt)

    if args.update_sample:
        print("==> Refreshing sample/ artifacts")
        _copy_sample(bundle, summary, parity, out)

    print()
    print("Done. Ownable artifacts:")
    print(f"  OKF bundle:  {bundle}")
    print(f"  Summary:     {out / 'migration_summary.json'}")
    print(f"  Recall:      {out / 'recall-parity.md'}")
    if not parity["is_recall_preserved"]:
        print("ERROR: recall parity failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
