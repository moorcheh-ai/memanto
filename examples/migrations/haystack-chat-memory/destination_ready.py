"""Wait for real namespace ingestion; queued importer success is not completion."""

import os
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch


def main() -> None:
    with patch.object(
        Path, "home", return_value=Path(os.environ["HAYSTACK_MEMANTO_CONFIG"]).resolve()
    ):
        from memanto.app.clients.moorcheh import get_moorcheh_client

        client = get_moorcheh_client()
        target = f"memanto_agent_{sys.argv[1]}"
        expected = int(sys.argv[2])
        deadline = time.monotonic() + 45
        previous = None
        while time.monotonic() < deadline:
            entries = client.namespaces.list().get("namespaces", [])
            namespace: dict[str, Any] = next(
                (row for row in entries if row.get("namespace_name") == target), {}
            )
            count = namespace.get("item_count", 0)
            if count != previous:
                print(
                    f"Destination ingestion: {count}/{expected} records persisted.",
                    flush=True,
                )
                previous = count
            if count == expected:
                return
            if count > expected:
                raise SystemExit("Unexpected extra records in dedicated destination")
            time.sleep(1)
        raise SystemExit(
            f"Destination never reached {expected} records; full export parity cannot pass"
        )


if __name__ == "__main__":
    main()
