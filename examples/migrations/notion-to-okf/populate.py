"""
populate.py
===========
Notion → Memanto migration showcase — one-command runner.

Pipeline:
  1. Load a pre-exported Notion JSON (from ``data/notion_export.json``)
     OR fetch live from Notion API (requires NOTION_API_KEY + DATABASE_IDs)
  2. Map pages → Memanto memory payloads via ``notion_adapter.map_notion``
  3. Dry-run: print mapped preview + savings report (no writes)
  4. Live: batch-import into Memanto via the SDK client
  5. Export imported memories out to portable OKF via the export service
  6. Round-trip validation: recall 6 golden questions before and after OKF export

Usage:
  python populate.py --dry-run          # preview only, no writes
  python populate.py                    # full run (needs MOORCHEH_API_KEY)
  python populate.py --skip-export      # import only, skip OKF export
  python populate.py --notion-live      # fetch from real Notion API

Environment:
  MOORCHEH_API_KEY    — required for live import
  MOORCHEH_AGENT_ID   — agent to import into (default: notion-migration-demo)
  NOTION_API_KEY      — required only for --notion-live
  NOTION_DATABASE_IDS — comma-separated Notion database IDs (for --notion-live)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
SAMPLE_EXPORT = DATA_DIR / "notion_export.json"

# ── Golden Q&A for round-trip validation ──────────────────────────────────────

GOLDEN_QA: list[dict] = [
    {
        "id": "Q001",
        "question": "What decision was made about the memory backend?",
        "must_contain": ["Pinecone", "Memanto"],
        "query_type": "decision",
    },
    {
        "id": "Q002",
        "question": "What is the user's preference for API response time?",
        "must_contain": ["500ms"],
        "query_type": "preference",
    },
    {
        "id": "Q003",
        "question": "What was agreed in the Q3 planning meeting?",
        "must_contain": ["temporal recall"],
        "query_type": "event",
    },
    {
        "id": "Q004",
        "question": "What was the bug found in the datetime handling?",
        "must_contain": ["utcnow", "timezone"],
        "query_type": "fact",
    },
    {
        "id": "Q005",
        "question": "What benchmark was used to evaluate Memanto?",
        "must_contain": ["LoCoMo"],
        "query_type": "fact",
    },
    {
        "id": "Q006",
        "question": "What is the goal for the Memanto bug bounty?",
        "must_contain": ["bugs", "PR"],
        "query_type": "goal",
    },
]


# ── Notion live fetch (optional) ───────────────────────────────────────────────


def fetch_notion_export(api_key: str, database_ids: list[str]) -> dict:
    """
    Fetch pages from Notion API and return in the standard export shape.

    Queries each database_id via the Notion search/query API and assembles
    a pages list. Requires the ``notion-client`` package:
        pip install notion-client
    """
    try:
        from notion_client import Client  # type: ignore
    except ImportError:
        print("❌ notion-client not installed. Run: pip install notion-client")
        sys.exit(1)

    client = Client(auth=api_key)
    pages = []

    for db_id in database_ids:
        print(f"  Fetching database {db_id}...")
        has_more = True
        cursor = None
        db_name = db_id  # will be overwritten by first page

        while has_more:
            kwargs: dict = {"database_id": db_id, "page_size": 100}
            if cursor:
                kwargs["start_cursor"] = cursor

            response = client.databases.query(**kwargs)

            for result in response.get("results", []):
                page_id = result["id"]
                props = result.get("properties", {})

                # Extract title
                title = ""
                for key in ("Name", "Title", "title", "name"):
                    if key in props:
                        title_prop = props[key]
                        rich_text = (
                            title_prop.get("title") or title_prop.get("rich_text") or []
                        )
                        title = "".join(t.get("plain_text", "") for t in rich_text)
                        if title:
                            break

                # Flatten properties
                flat_props: dict = {}
                for pname, pval in props.items():
                    ptype = pval.get("type")
                    if ptype == "multi_select":
                        flat_props[pname] = [
                            o["name"] for o in pval.get("multi_select", [])
                        ]
                    elif ptype == "select" and pval.get("select"):
                        flat_props[pname] = pval["select"]["name"]
                    elif ptype == "rich_text":
                        flat_props[pname] = "".join(
                            t.get("plain_text", "") for t in pval.get("rich_text", [])
                        )
                    elif ptype == "date" and pval.get("date"):
                        flat_props[pname] = pval["date"].get("start")
                    elif ptype == "people":
                        flat_props[pname] = [
                            p.get("name", "") for p in pval.get("people", [])
                        ]
                    elif ptype == "checkbox":
                        flat_props[pname] = pval.get("checkbox")

                # Fetch page content (blocks)
                blocks = client.blocks.children.list(block_id=page_id)
                content_lines = []
                for block in blocks.get("results", []):
                    btype = block.get("type")
                    if btype in (
                        "paragraph",
                        "heading_1",
                        "heading_2",
                        "heading_3",
                        "bulleted_list_item",
                        "numbered_list_item",
                        "quote",
                    ):
                        rich_text = block.get(btype, {}).get("rich_text", [])
                        text = "".join(t.get("plain_text", "") for t in rich_text)
                        if text:
                            content_lines.append(text)

                db_name = db_id  # ideally fetch DB name but keep simple
                pages.append(
                    {
                        "id": page_id,
                        "database": db_name,
                        "title": title,
                        "created_time": result.get("created_time"),
                        "last_edited_time": result.get("last_edited_time"),
                        "properties": flat_props,
                        "content": "\n".join(content_lines),
                        "url": result.get("url", ""),
                    }
                )

            has_more = response.get("has_more", False)
            cursor = response.get("next_cursor")

    return {
        "export_metadata": {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "notion_workspace": "live",
            "exporter_version": "1.0.0",
            "databases": database_ids,
        },
        "pages": pages,
    }


# ── Keyword recall scorer ──────────────────────────────────────────────────────


def score_recall(answer: str, must_contain: list[str]) -> float:
    """Simple keyword scorer — 1.0 if all keywords present, else partial."""
    if not answer:
        return 0.0
    lower = answer.lower()
    hits = sum(1 for kw in must_contain if kw.lower() in lower)
    return round(hits / len(must_contain), 2) if must_contain else 1.0


# ── Migration savings report ───────────────────────────────────────────────────


def print_savings_report(
    pages: list[dict],
    rows: list[dict],
    import_latency_s: float,
) -> None:
    """Print a structured migration savings summary."""
    source_tokens = sum(
        len(p.get("content") or p.get("title") or "") // 4 for p in pages
    )
    mapped_tokens = sum(len(r.get("content", "")) // 4 for r in rows)
    type_counts: dict[str, int] = {}
    for r in rows:
        k = r.get("type") or "auto"
        type_counts[k] = type_counts.get(k, 0) + 1

    dbs = list(dict.fromkeys(p.get("database", "unknown") for p in pages))

    print("\n" + "=" * 60)
    print("  MIGRATION SUMMARY — Notion → Memanto")
    print("=" * 60)
    print(f"  Source pages          : {len(pages)}")
    print(f"  Mapped memories       : {len(rows)}")
    print(f"  Skipped               : {len(pages) - len(rows)}")
    print(f"  Source databases      : {', '.join(dbs)}")
    print(f"  Source tokens (est.)  : {source_tokens:,}")
    print(f"  Mapped tokens (est.)  : {mapped_tokens:,}")
    print(f"  Import latency        : {import_latency_s:.2f}s")
    print()
    print("  Memory types:")
    for t, n in sorted(type_counts.items()):
        print(f"    {t:<20} {n}")
    print("=" * 60)


# ── Round-trip validation ──────────────────────────────────────────────────────


def run_golden_recall(client: object, agent_id: str, label: str) -> list[dict]:
    """Run golden Q&A recall against live Memanto and return scored results."""
    results = []
    print(f"\n🔍 {label} ({len(GOLDEN_QA)} questions)...")
    for qa in GOLDEN_QA:
        try:
            resp = client.recall(agent_id=agent_id, query=qa["question"], limit=5)  # type: ignore[attr-defined]
            memories = resp.get("results", []) if isinstance(resp, dict) else []
            answer = " ".join(m.get("content", "") for m in memories)
            score = score_recall(answer, qa["must_contain"])
        except Exception as e:
            answer = ""
            score = 0.0
            print(f"    ⚠️  {qa['id']} recall error: {e}")

        results.append(
            {
                "id": qa["id"],
                "question": qa["question"],
                "score": score,
                "answer_preview": answer[:120] + "..." if len(answer) > 120 else answer,
            }
        )
        status = "✅" if score >= 0.5 else "❌"
        print(f"    {status} {qa['id']} score={score:.2f} — {qa['question'][:60]}")

    avg = sum(r["score"] for r in results) / len(results) if results else 0
    print(
        f"  Average: {avg:.1%}  ({sum(1 for r in results if r['score'] >= 0.5)}/{len(results)} passing)"
    )
    return results


# ── Main ───────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Notion → Memanto → OKF migration showcase"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview only, no writes"
    )
    parser.add_argument(
        "--skip-export", action="store_true", help="Skip OKF export step"
    )
    parser.add_argument(
        "--notion-live", action="store_true", help="Fetch from live Notion API"
    )
    parser.add_argument(
        "--agent-id", default="notion-migration-demo", help="Memanto agent ID"
    )
    parser.add_argument(
        "--file", type=Path, default=SAMPLE_EXPORT, help="Path to Notion export JSON"
    )
    args = parser.parse_args()

    print("🚀 Notion → Memanto → OKF Migration")
    print(f"   Agent: {args.agent_id}")
    if args.dry_run:
        print("   Mode: DRY RUN (no writes)\n")
    else:
        print("   Mode: LIVE\n")

    # Step 1: Load export
    if args.notion_live:
        api_key = os.getenv("NOTION_API_KEY", "")
        db_ids_raw = os.getenv("NOTION_DATABASE_IDS", "")
        if not api_key or not db_ids_raw:
            print("❌ Set NOTION_API_KEY and NOTION_DATABASE_IDS for live fetch")
            sys.exit(1)
        db_ids = [d.strip() for d in db_ids_raw.split(",") if d.strip()]
        print(f"📡 Fetching from Notion API ({len(db_ids)} databases)...")
        export = fetch_notion_export(api_key, db_ids)
        out_path = DATA_DIR / "notion_export_live.json"
        out_path.write_text(json.dumps(export, indent=2, default=str), encoding="utf-8")
        print(f"   Saved to {out_path}")
    else:
        if not args.file.exists():
            print(f"❌ Export file not found: {args.file}")
            print("   Run with --notion-live to fetch from Notion API,")
            print("   or ensure data/notion_export.json exists.")
            sys.exit(1)
        export = json.loads(args.file.read_text(encoding="utf-8"))
        print(f"📂 Loaded export: {args.file}")

    pages = export.get("pages", [])
    print(f"   {len(pages)} pages found")

    # Step 2: Map
    sys.path.insert(0, str(HERE))
    from notion_adapter import map_notion

    rows = map_notion(export)
    print(f"   {len(rows)} memories mapped ({len(pages) - len(rows)} skipped)")

    # Preview
    preview_path = HERE / "migration_preview.json"
    preview_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"   Preview written → {preview_path}")

    if args.dry_run:
        print_savings_report(pages, rows, 0.0)
        print("\n✅ Dry run complete. No writes performed.")
        return

    # Step 3: Import into Memanto
    moorcheh_key = os.getenv("MOORCHEH_API_KEY", "")
    if not moorcheh_key:
        print("❌ MOORCHEH_API_KEY required for live import. Use --dry-run to preview.")
        sys.exit(1)

    try:
        from memanto.cli.client.sdk_client import SdkClient

        client = SdkClient(api_key=moorcheh_key)
        # Create agent if it does not exist, then activate a session
        try:
            client.create_agent(args.agent_id)
            print(f"  ✅ Agent '{args.agent_id}' created")
        except Exception:
            pass  # agent already exists
        client.activate_agent(args.agent_id)
    except Exception as e:
        print(f"❌ Failed to initialise Memanto client: {e}")
        sys.exit(1)

    print(f"\n📤 Importing {len(rows)} memories → agent '{args.agent_id}'...")
    t0 = time.perf_counter()
    imported = failed = 0
    batch_size = 100

    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        try:
            result = client.batch_remember(agent_id=args.agent_id, memories=batch)
            imported += result.get("successful", 0)
            failed += result.get("failed", 0)
            print(
                f"  Batch {i // batch_size + 1}: {result.get('successful', 0)} ok, {result.get('failed', 0)} failed"
            )
        except Exception as e:
            print(f"  ❌ Batch {i // batch_size + 1} error: {e}")
            failed += len(batch)

    import_latency = time.perf_counter() - t0
    print(f"  ✅ Imported: {imported}  ❌ Failed: {failed}  ⏱ {import_latency:.2f}s")
    print_savings_report(pages, rows, import_latency)

    # Step 4: Golden recall — before OKF export
    pre_recall = run_golden_recall(client, args.agent_id, "Pre-export recall (Memanto)")

    if args.skip_export:
        print("\n⏭  Skipping OKF export (--skip-export)")
        return

    # Step 5: OKF export
    print("\n📦 Exporting memories to OKF bundle...")
    try:
        from moorcheh_sdk import MoorchehClient

        from memanto.app.core import agent_namespace
        from memanto.app.services.memory_read_service import MemoryReadService
        from memanto.app.services.okf_export_service import OkfExportService

        moorcheh_client = MoorchehClient(api_key=moorcheh_key)
        read_svc = MemoryReadService(moorcheh_client)
        okf_svc = OkfExportService()

        # Fetch all memories grouped by type
        all_memories = read_svc._fetch_all_memories([agent_namespace(args.agent_id)])
        memories_by_type: dict[str, list] = {}
        for mem in all_memories:
            t = mem.get("type") or "fact"
            memories_by_type.setdefault(t, []).append(mem)

        bundle_dir = HERE / "okf_bundle_live"
        result = okf_svc.write_okf_bundle(
            agent_id=args.agent_id,
            memories_by_type=memories_by_type,
            output_dir=bundle_dir,
        )
        print(f"  ✅ OKF bundle written → {bundle_dir}")
        print(
            f"     {result.get('total_memories', 0)} memories, sections: {result.get('sections', [])}"
        )

        # Step 6: Round-trip — import OKF back and recall
        print("\n🔄 Round-trip: importing OKF bundle back into Memanto...")
        from memanto.cli.migrate.mappers import map_okf
        from memanto.cli.migrate.okf_loader import load_okf_bundle

        okf_export = load_okf_bundle(bundle_dir)
        okf_rows = map_okf(okf_export)
        rt_agent = f"{args.agent_id}-okf-roundtrip"

        rt_result = client.batch_remember(agent_id=rt_agent, memories=okf_rows)
        print(f"  ✅ OKF round-trip import: {rt_result.get('successful', 0)} ok")

        time.sleep(2)  # let Moorcheh index
        post_recall = run_golden_recall(
            client, rt_agent, "Post-export recall (OKF round-trip)"
        )

        # Summary
        pre_avg = (
            sum(r["score"] for r in pre_recall) / len(pre_recall) if pre_recall else 0
        )
        post_avg = (
            sum(r["score"] for r in post_recall) / len(post_recall)
            if post_recall
            else 0
        )
        print(
            f"\n📊 Recall parity: Memanto={pre_avg:.1%}  OKF round-trip={post_avg:.1%}"
        )

        # Save validation report
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": args.agent_id,
            "pages_source": len(pages),
            "memories_mapped": len(rows),
            "memories_imported": imported,
            "okf_memories": result.get("total_memories", 0),
            "pre_export_recall": pre_recall,
            "post_export_recall": post_recall,
            "recall_parity_pre": round(pre_avg, 3),
            "recall_parity_post": round(post_avg, 3),
        }
        report_path = HERE / "validation_report.json"
        report_path.write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )
        print(f"\n💾 Validation report → {report_path}")

    except Exception as e:
        print(f"⚠️  OKF export step failed: {e}")
        print("    Import succeeded — OKF export requires local Memanto server.")

    print("\n✅ Migration complete.")


if __name__ == "__main__":
    main()
