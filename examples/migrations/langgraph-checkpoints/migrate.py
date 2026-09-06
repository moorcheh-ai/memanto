"""CLI for converting LangGraph SQLite checkpoints to OKF."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from langgraph_checkpoint_to_okf import convert_database


def _channel_type(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected CHANNEL=TYPE")
    channel, memory_type = value.split("=", 1)
    return channel.strip(), memory_type.strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert current LangGraph SQLite checkpoint state to OKF."
    )
    parser.add_argument("database", type=Path, help="SqliteSaver database path")
    parser.add_argument("output", type=Path, help="new OKF bundle directory")
    parser.add_argument(
        "--thread",
        action="append",
        dest="threads",
        help="include only this thread_id (repeatable)",
    )
    parser.add_argument(
        "--exclude-channel",
        action="append",
        default=[],
        help="exclude a transient/private channel (repeatable)",
    )
    parser.add_argument(
        "--channel-type",
        action="append",
        default=[],
        type=_channel_type,
        metavar="CHANNEL=TYPE",
        help="override a channel's Memanto type",
    )
    args = parser.parse_args()

    output, checkpoints, records = convert_database(
        args.database,
        args.output,
        thread_ids=args.threads,
        excluded_channels=args.exclude_channel,
        channel_types=dict(args.channel_type),
    )
    summary = {
        "database": str(args.database),
        "output": str(output),
        "threads": sorted({item.thread_id for item in checkpoints}),
        "checkpoints": len(checkpoints),
        "records": len(records),
        "per_type": {
            memory_type: sum(record.memory_type == memory_type for record in records)
            for memory_type in sorted({record.memory_type for record in records})
        },
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
