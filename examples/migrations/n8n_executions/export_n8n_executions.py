"""Export full n8n executions through the supported public API.

The output is deliberately kept local. Execution payloads can contain personal
data or credentials; ``adapter.py`` copies only allow-listed mapping fields into
the OKF bundle.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


def export_executions(
    base_url: str,
    api_key: str,
    *,
    limit: int = 100,
    workflow_id: str | None = None,
    status: str | None = None,
) -> dict:
    """Page through n8n's public API and return full execution objects."""
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be an absolute http(s) URL")
    loopback_hosts = {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme == "http" and parsed.hostname not in loopback_hosts:
        raise ValueError("remote n8n endpoints must use https; http is loopback-only")

    executions: list[dict] = []
    cursor: str | None = None

    while True:
        params = {"includeData": "true", "limit": str(min(limit, 250))}
        if workflow_id:
            params["workflowId"] = workflow_id
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor

        request = Request(
            f"{base_url.rstrip('/')}/api/v1/executions?{urlencode(params)}",
            headers={
                "Accept": "application/json",
                "X-N8N-API-KEY": api_key,
            },
        )
        with urlopen(request, timeout=30) as response:  # noqa: S310
            page = json.load(response)

        rows = page.get("data")
        if not isinstance(rows, list):
            raise ValueError("n8n API response does not contain a data list")
        executions.extend(rows)
        if len(executions) >= limit:
            executions = executions[:limit]
            break
        next_cursor = page.get("nextCursor")
        if next_cursor is not None and not isinstance(next_cursor, str):
            raise ValueError("n8n API nextCursor must be a string or null")
        if next_cursor == cursor:
            raise ValueError("n8n API pagination made no progress")
        cursor = next_cursor
        if not cursor:
            break

    return {"data": executions}


def main() -> int:
    """Export executions to a local JSON file and return a process exit code."""
    parser = argparse.ArgumentParser(description="Export full n8n executions.")
    parser.add_argument("--base-url", default="http://localhost:5679")
    parser.add_argument("--api-key", default=os.getenv("N8N_API_KEY"))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--workflow-id")
    parser.add_argument("--status", choices=("success", "error", "waiting"))
    parser.add_argument("--output", default="n8n-executions.private.json")
    args = parser.parse_args()

    if not args.api_key:
        parser.error("Provide --api-key or set N8N_API_KEY")
    if args.limit < 1:
        parser.error("--limit must be positive")

    output = Path(args.output)
    payload = export_executions(
        args.base_url,
        args.api_key,
        limit=args.limit,
        workflow_id=args.workflow_id,
        status=args.status,
    )
    output.write_bytes(
        (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )
    print(f"Exported {len(payload['data'])} execution(s) to {output.resolve()}")
    print("Treat the source export as private; it may contain sensitive payloads.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
