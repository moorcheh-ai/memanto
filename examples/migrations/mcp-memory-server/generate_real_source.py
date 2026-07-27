#!/usr/bin/env python3
"""Populate a genuine MCP Memory Server graph through its stdio protocol.

This script launches the official ``@modelcontextprotocol/server-memory``
package and calls its public tools.  It does not hand-write ``memory.jsonl``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

PACKAGE = "@modelcontextprotocol/server-memory@2026.7.4"
PROTOCOL_VERSION = "2025-06-18"


class McpStdioClient:
    def __init__(self, memory_file: Path) -> None:
        env = os.environ.copy()
        env["MEMORY_FILE_PATH"] = str(memory_file.resolve())
        self.process = subprocess.Popen(
            ["npx", "-y", PACKAGE],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        self.next_id = 1

    def _send(self, message: dict[str, Any]) -> None:
        if self.process.stdin is None:
            raise RuntimeError("MCP server stdin is unavailable")
        self.process.stdin.write(
            json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"
        )
        self.process.stdin.flush()

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._send(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {},
            }
        )

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self.next_id
        self.next_id += 1
        self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        if self.process.stdout is None:
            raise RuntimeError("MCP server stdout is unavailable")
        while True:
            line = self.process.stdout.readline()
            if not line:
                stderr = (
                    self.process.stderr.read()
                    if self.process.stderr is not None
                    else ""
                )
                raise RuntimeError(
                    f"MCP server exited before response {request_id}: {stderr}"
                )
            message = json.loads(line)
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(f"MCP request {method} failed: {message['error']}")
            result = message.get("result")
            if not isinstance(result, dict):
                raise RuntimeError(f"MCP request {method} returned no result")
            return result

    def initialize(self) -> None:
        self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "memanto-mcp-memory-migration-showcase",
                    "version": "1.0.0",
                },
            },
        )
        self.notify("notifications/initialized")

    def call_tool(self, name: str, arguments: dict[str, Any]) -> None:
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise RuntimeError(f"MCP tool {name} returned an error: {result}")

    def close(self) -> None:
        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)


def populate(memory_file: Path, *, force: bool = False) -> None:
    if memory_file.exists():
        if not force:
            raise FileExistsError(
                f"source already exists: {memory_file} (pass --force to replace it)"
            )
        memory_file.unlink()
    memory_file.parent.mkdir(parents=True, exist_ok=True)

    client = McpStdioClient(memory_file)
    try:
        client.initialize()

        # Session 1: capture the components discovered during repository research.
        client.call_tool(
            "create_entities",
            {
                "entities": [
                    {
                        "name": "MCP Memory Server Adapter",
                        "entityType": "project",
                        "observations": [
                            "Transforms the official MCP Memory Server JSONL "
                            "knowledge graph into portable OKF Markdown.",
                            "Chosen after a repository search found no existing "
                            "MCP Memory migration submission on 2026-07-27.",
                        ],
                    },
                    {
                        "name": "Official MCP Memory Server",
                        "entityType": "tool",
                        "observations": [
                            "Stores entities and relations as newline-delimited JSON.",
                            "The package version pinned for this reproducible "
                            "showcase is 2026.7.4.",
                        ],
                    },
                    {
                        "name": "Memanto OKF Loader",
                        "entityType": "component",
                        "observations": [
                            "Imports Markdown documents from the memories directory.",
                            "Preserves unknown OKF frontmatter in a Supporting data footer.",
                        ],
                    },
                    {
                        "name": "Memanto Bounty 1609",
                        "entityType": "bounty",
                        "observations": [
                            "Rewards a compelling reproducible migration showcase.",
                            "Path B gives highest engineering value to a new source adapter.",
                        ],
                    },
                    {
                        "name": "Portable OKF Bundle",
                        "entityType": "artifact",
                        "observations": [
                            "Keeps entity observations readable as Markdown.",
                            "Keeps graph relations navigable as typed links.",
                        ],
                    },
                ]
            },
        )
        client.call_tool(
            "create_relations",
            {
                "relations": [
                    {
                        "from": "MCP Memory Server Adapter",
                        "to": "Official MCP Memory Server",
                        "relationType": "reads",
                    },
                    {
                        "from": "MCP Memory Server Adapter",
                        "to": "Portable OKF Bundle",
                        "relationType": "produces",
                    },
                    {
                        "from": "Portable OKF Bundle",
                        "to": "Memanto OKF Loader",
                        "relationType": "is consumed by",
                    },
                    {
                        "from": "MCP Memory Server Adapter",
                        "to": "Memanto Bounty 1609",
                        "relationType": "targets",
                    },
                ]
            },
        )

        # Session 2: record implementation decisions learned from the source.
        client.call_tool(
            "add_observations",
            {
                "observations": [
                    {
                        "entityName": "MCP Memory Server Adapter",
                        "contents": [
                            "Uses one OKF document per entity and embeds exact "
                            "source records for lossless reconstruction.",
                            "Runs offline with no third-party Python dependencies.",
                        ],
                    },
                    {
                        "entityName": "Portable OKF Bundle",
                        "contents": [
                            "Copies the original memory.jsonl outside memories so "
                            "Memanto does not re-ingest it."
                        ],
                    },
                ]
            },
        )

        # Session 3: preserve a genuine correction in the project history.
        client.call_tool(
            "add_observations",
            {
                "observations": [
                    {
                        "entityName": "MCP Memory Server Adapter",
                        "contents": [
                            "The initial LangGraph direction was discarded after "
                            "active migration PRs were found."
                        ],
                    }
                ]
            },
        )
    finally:
        client.close()

    if not memory_file.exists() or not memory_file.read_text(encoding="utf-8").strip():
        raise RuntimeError("official MCP Memory Server produced no source data")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a real MCP Memory Server source graph."
    )
    parser.add_argument("--output", required=True, help="Output memory.jsonl")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        populate(Path(args.output), force=args.force)
    except (FileExistsError, RuntimeError) as exc:
        print(f"error: {exc}")
        return 2
    print(f"generated by {PACKAGE}: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
