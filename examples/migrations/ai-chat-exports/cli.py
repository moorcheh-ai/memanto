from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import adapters  # noqa: F401 (registers adapters)
from core.adapters import ADAPTERS, DataSource, load_source
from core.dedup import collect_existing_refs, dedupe_entities
from core.okf_generator import OKFGenerator


def build_filters(args: argparse.Namespace) -> dict:
    filters: dict = {}
    if args.filter:
        filters["keyword"] = args.filter
    if args.chats:
        filters["chat_ids"] = [c.strip() for c in args.chats.split(",")]
    if args.interactive:
        filters["interactive"] = True
    return filters


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Universal Migration Adapter — convert AI chat exports to OKF bundles for Memanto"
    )
    parser.add_argument(
        "--source",
        choices=list(ADAPTERS.keys()),
        required=True,
        help="Source tool to migrate from",
    )
    parser.add_argument(
        "--source-type",
        choices=["file", "api"],
        default="file",
        help="Source kind: 'file' (export path) or 'api' (live endpoint). "
        "API sources let you migrate from live agents without a file export.",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Path to source export file (JSON or ZIP) when --source-type file",
    )
    parser.add_argument(
        "--endpoint",
        default=None,
        help="API endpoint when --source-type api",
    )
    parser.add_argument(
        "--output",
        default="./okf_output",
        help="Output directory for OKF bundle (default: ./okf_output)",
    )
    parser.add_argument(
        "--filter",
        default=None,
        help="Filter memories by keyword",
    )
    parser.add_argument(
        "--chats",
        default=None,
        help="Filter by chat/conversation IDs (comma-separated)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive selection of memories",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing files",
    )
    parser.add_argument(
        "--dedupe-from-dir",
        default=None,
        metavar="DIR",
        help="Skip memories already present in an OKF bundle (by resource/source_ref). "
        "Point this at a previously exported bundle to avoid duplicate imports.",
    )

    args = parser.parse_args()

    if args.source_type == "file" and not args.input:
        parser.error("--input is required when --source-type file")
    if args.source_type == "api" and not args.endpoint:
        parser.error("--endpoint is required when --source-type api")

    if args.source_type == "file":
        source = DataSource.from_file(args.input)
    else:
        source = DataSource.from_api(args.endpoint)

    adapter_cls = ADAPTERS[args.source]
    adapter = adapter_cls()

    print(f"[1/4] Loading {args.source} export from {source.kind} source...")
    try:
        raw = load_source(adapter, source)
    except (FileNotFoundError, ValueError, PermissionError, TypeError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    filters = build_filters(args)

    if args.interactive:
        conv_list = adapter.get_conversation_list(raw)
        if not conv_list:
            print("No conversations found in the export.")
            sys.exit(1)

        print(f"\nFound {len(conv_list)} conversations:\n")
        for i, conv in enumerate(conv_list):
            print(
                f"  [{i + 1}] {conv['title'][:60]}  ({conv['message_count']} messages)"
            )

        print("\n  [a] Select all")
        print("  [q] Quit\n")

        while True:
            raw_input = input(
                "Enter numbers (comma-separated) or 'a' for all: "
            ).strip()
            if raw_input == "q":
                print("Aborted.")
                sys.exit(0)
            if raw_input == "a":
                break
            parts = [p for p in re.split(r"[\s,]+", raw_input) if p]
            try:
                indices = [int(p) for p in parts]
            except ValueError:
                print(
                    "Invalid input: enter conversation numbers separated by commas (e.g. 1,3,5) or 'a' for all. Please try again:"
                )
                continue
            if not indices:
                print("Empty input. Please try again:")
                continue
            bad = [i for i in indices if i < 1 or i > len(conv_list)]
            if bad:
                print(
                    f"Invalid number(s) {bad}: there are only {len(conv_list)} conversations. Please try again:"
                )
                continue
            filters["chat_ids"] = [conv_list[i - 1]["id"] for i in indices]
            break

    print("\n[2/4] Extracting memories...")
    entities = adapter.extract(raw, filters)

    if not entities:
        print("No memories found. Check your filters or input file.")
        sys.exit(1)

    print(f"       Found {len(entities)} memories")

    if args.dedupe_from_dir:
        existing = collect_existing_refs(args.dedupe_from_dir)
        if existing:
            entities, skipped = dedupe_entities(entities, existing)
            print(
                f"       Dedupe: skipped {len(skipped)} already-imported, "
                f"keeping {len(entities)}"
            )
        else:
            print(f"       Dedupe: no existing refs found in {args.dedupe_from_dir}")

    if args.dry_run:
        print("\n--- Dry Run Preview ---")
        for i, mem in enumerate(entities[:10]):
            print(f"  [{i + 1}] [{mem.source_type.value}] {mem.title[:60]}")
            print(f"      Tags: {', '.join(mem.tags)}")
            if mem.timestamp:
                print(f"      Date: {mem.timestamp.isoformat()}")
            print()
        if len(entities) > 10:
            print(f"  ... and {len(entities) - 10} more")
        print("\nRun without --dry-run to write OKF bundle.")
        return

    print(f"[3/4] Generating OKF bundle at {args.output}...")
    generator = OKFGenerator(args.output)
    output_path = generator.generate_bundle(entities)

    print("[4/4] Done!")
    print(f"\n{'=' * 50}")
    print(f"OKF bundle created at: {output_path}")
    print(f"Total memories: {len(entities)}")
    print(f"{'=' * 50}")
    print("\nNext step:")
    print(f"  memanto migrate okf {output_path} --dry-run")


if __name__ == "__main__":
    main()
