"""Check four golden questions using the shipped SDK's actual destination semantic recall."""

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch


def main() -> None:
    with patch.object(
        Path, "home", return_value=Path(os.environ["HAYSTACK_MEMANTO_CONFIG"]).resolve()
    ):
        from adapter import reconstruct
        from source_history import GOLDEN, answer

        from memanto.cli.commands._shared import get_client

        client = get_client()
        checks = {}
        for key, expected in GOLDEN.items():
            query = f"What is the latest procurement {key.replace('_', ' ')} setting?"
            response = client.recall(
                agent_id=sys.argv[1], query=query, limit=20, min_similarity=0.0
            )
            envelopes = [reconstruct(row["content"]) for row in response["memories"]]
            envelopes.sort(key=lambda row: row["position"])
            actual = answer([row["message"] for row in envelopes], key)
            checks[key] = {
                "query": query,
                "expected": expected,
                "actual": actual,
                "returned_memories": len(envelopes),
                "passed": actual == expected,
            }
            print(json.dumps(checks[key]), flush=True)
            if os.environ.get("HAYSTACK_DEMO") == "1":
                print(
                    "[Presentation pause: 4s; not a retrieval latency measurement]",
                    flush=True,
                )
                time.sleep(4)
        Path(sys.argv[2]).write_text(
            json.dumps(
                {
                    "mode": "LIVE_MEMANTO_ON_PREM_RECALL"
                    if os.environ.get("MEMANTO_BACKEND") == "on-prem"
                    else "LIVE_MOORCHEH_CLOUD_RECALL",
                    "method": "semantic retrieve up to 20 memories, then deterministic latest-setting answer over source positions",
                    "checks": checks,
                },
                indent=2,
            )
            + "\n"
        )
        if not all(row["passed"] for row in checks.values()):
            raise SystemExit("Destination recall golden parity failed")


if __name__ == "__main__":
    main()
