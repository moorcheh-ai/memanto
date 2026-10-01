"""One-command LangMem -> Memanto (OKF) migration.

    python run.py                 # full offline pipeline (no keys needed)
    python run.py --extract live  # use an LLM to extract memories from the transcript
    python run.py --import-memanto --agent alex   # also import into a live Memanto agent

Pipeline:
    1. populate  a LangMem store from the scripted 3-week history
    2. export    the store -> artifacts/langmem_export.json
    3. adapt     the export -> artifacts/okf-bundle/  (valid OKF)
    4. validate  before/after recall parity -> artifacts/validation-report.md
    5. summarize -> artifacts/migration-summary.md

Everything except step 3's optional live import runs offline and
deterministically, so the committed artifacts reproduce exactly.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--extract", choices=["replay", "live"], default="replay")
    parser.add_argument("--model", default="openai:gpt-4o-mini")
    parser.add_argument("--after", choices=["bundle", "memanto"], default="bundle")
    parser.add_argument(
        "--import-memanto",
        action="store_true",
        help="Run `memanto migrate okf` on the bundle (needs MOORCHEH_API_KEY + active agent).",
    )
    parser.add_argument(
        "--agent", default=None, help="Target Memanto agent id for import/validation."
    )
    args = parser.parse_args()

    # Imported here so `python run.py` works from the example dir.
    from langmem_migration import validate as V
    from langmem_migration.adapter import write_okf_bundle
    from langmem_migration.export import export_store, write_export
    from langmem_migration.mapping import type_breakdown
    from langmem_migration.populate import build_store

    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    print(f"1/5  Populating a LangMem store (extract={args.extract})...")
    store = build_store(extract=args.extract, model=args.model)

    print("2/5  Exporting the LangMem store...")
    export = export_store(store)
    export_path = write_export(store, ARTIFACTS / "langmem_export.json")
    print(f"      -> {export_path.relative_to(HERE)} ({export['count']} memories)")

    print("3/5  Adapting LangMem export -> OKF bundle...")
    bundle_dir = ARTIFACTS / "okf-bundle"
    summary = write_okf_bundle(
        export, bundle_dir, agent_id=args.agent or "langmem-import"
    )
    print(f"      -> {bundle_dir.relative_to(HERE)}  types: {summary['type_counts']}")

    if args.import_memanto:
        print("3b/5 Importing bundle into Memanto (memanto migrate okf)...")
        _memanto_import(bundle_dir, args.agent)

    print(f"4/5  Validating recall parity (after={args.after})...")
    report = V.validate(store, export, after=args.after, agent_id=args.agent)
    (ARTIFACTS / "validation-report.md").write_text(
        V.render_markdown(report), encoding="utf-8"
    )
    print(
        f"      before {report['before_pass']}/{report['n']}  "
        f"after {report['after_pass']}/{report['n']}  "
        f"parity {report['parity_pct']}%"
    )

    print("5/5  Writing migration summary + mapping table...")
    _write_summary(summary, report, extract=args.extract)
    _write_mapping_table(export, type_breakdown)

    print("\nDone. Artifacts in ./artifacts/:")
    for p in sorted(ARTIFACTS.rglob("*")):
        if p.is_file() and p.suffix in {".json", ".md"} and p.parent == ARTIFACTS:
            print(f"  {p.relative_to(HERE)}")
    if report["after_pass"] < report["before_pass"]:
        print(
            "\nWARNING: recall dropped after migration — investigate before claiming parity."
        )
        sys.exit(1)


def _memanto_import(bundle_dir: Path, agent: str | None) -> None:
    cmd = [sys.executable, "-m", "memanto", "migrate", "okf", str(bundle_dir)]
    if agent:
        cmd += ["--agent", agent]
    try:
        subprocess.run(cmd, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(
            f"      migrate okf failed: {exc}\n"
            "      (needs MOORCHEH_API_KEY and an active agent — see README)"
        )


def _write_summary(summary: dict, report: dict, extract: str) -> None:
    lines = [
        "# Migration summary — LangMem -> Memanto (OKF)",
        "",
        f"- Extraction backend: **{extract}**",
        f"- Source LangMem memories: **{summary['source_count']}**",
        f"- Mapped Memanto memories: **{summary['mapped_count']}**",
        f"- OKF bundle sections: {', '.join(summary['sections'])}",
        "",
        "## Type breakdown (inferred from untyped LangMem content)",
        "",
        "| Memanto type | Count |",
        "| --- | :---: |",
    ]
    for t, c in summary["type_counts"].items():
        lines.append(f"| {t} | {c} |")
    lines += [
        "",
        "## Recall parity (before vs after)",
        "",
        f"- Before (LangMem): {report['before_pass']}/{report['n']} ({report['before_pct']}%)",
        f"- After (Memanto):  {report['after_pass']}/{report['n']} ({report['after_pct']}%)",
        f"- Parity: {report['parity_pct']}%",
        "",
        "See `validation-report.md` for the per-question breakdown and "
        "`okf-bundle/` for the human-readable, portable memory bundle.",
        "",
    ]
    (ARTIFACTS / "migration-summary.md").write_text("\n".join(lines), encoding="utf-8")


def _write_mapping_table(export: dict, type_breakdown) -> None:
    from langmem_migration.mapping import map_record

    rows = [
        map_record(r)
        for r in export["memories"]
        if (r.get("value") or {}).get("content")
    ]
    lines = [
        "# LangMem -> Memanto / OKF field mapping",
        "",
        "| LangMem field | Memanto / OKF field | Notes |",
        "| --- | --- | --- |",
        "| `value.content` | memory body + derived `title` | verbatim, never lossy |",
        "| `namespace[1]` (user id) | tag `user=<id>`, `x_memanto.source=langmem` | scope preserved |",
        "| `key` (uuid) | `source_ref` / OKF `resource` `langmem:<key>` | back-reference |",
        "| `created_at` | OKF `timestamp` | temporal recall fidelity |",
        "| *(inferred)* | memory `type` -> `x_memanto.type` | deterministic classifier |",
        "| *(constant)* | `provenance=imported`, `confidence=0.75` | migration marker |",
        "",
        "## Per-memory resolution",
        "",
        "| # | Inferred type | Title |",
        "| :---: | --- | --- |",
    ]
    for i, row in enumerate(rows, 1):
        lines.append(f"| {i} | {row['type']} | {row['title']} |")
    lines.append("")
    (ARTIFACTS / "mapping-table.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
