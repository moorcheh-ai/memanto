"""Export opencode sessions to JSON (read-only).

Reads the local opencode SQLite store (``~/.local/share/opencode/opencode.db``)
without writing to it (immutable URI + read-only connection) and dumps
sessions, messages and parts to ``opencode_export.json``.

Usage:
    python export_opencode.py [--db PATH] [--out opencode_export.json]
        [--project PROJECT_ID] [--limit N] [--include-tool-payloads]

By default tool inputs and outputs are REDACTED (replaced with a placeholder)
because they routinely contain secrets (tokens, file contents, credentials).
Truncation is not redaction. Pass --include-tool-payloads only for data you
are willing to publish, and never commit such exports.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

DEFAULT_DB = Path.home() / ".local/share/opencode" / "opencode.db"
TOOL_OUTPUT_TRUNCATE = 500


def _connect(db: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def export_sessions(
    db: Path,
    *,
    project: str | None = None,
    limit: int = 0,
    include_tool_payloads: bool = False,
) -> dict:
    con = _connect(db)
    q = "SELECT * FROM session"
    params: list = []
    if project:
        q += " WHERE project_id = ?"
        params.append(project)
    q += " ORDER BY time_updated DESC"
    if limit:
        q += " LIMIT ?"
        params.append(limit)
    sessions = [dict(r) for r in con.execute(q, params)]

    out: dict = {"source": "opencode", "sessions": []}
    for s in sessions:
        sid = s["id"]
        messages = []
        for m in con.execute(
            "SELECT * FROM message WHERE session_id = ? ORDER BY time_created",
            (sid,),
        ):
            md = dict(m)
            try:
                data = json.loads(md.pop("data"))
            except (TypeError, json.JSONDecodeError):
                data = {}
            parts = []
            for p in con.execute(
                "SELECT * FROM part WHERE message_id = ? ORDER BY time_created",
                (md["id"],),
            ):
                pd = dict(p)
                try:
                    pdata = json.loads(pd.pop("data"))
                except (TypeError, json.JSONDecodeError):
                    pdata = {}
                if pdata.get("type") == "tool" and isinstance(pdata.get("state"), dict):
                    state = dict(pdata["state"])
                    if include_tool_payloads:
                        output = state.get("output")
                        if isinstance(output, str) and len(output) > TOOL_OUTPUT_TRUNCATE:
                            state["output"] = output[:TOOL_OUTPUT_TRUNCATE] + "\n…[truncated]"
                            pdata["state"] = state
                    else:
                        tool_name = pdata.get("tool", "tool")
                        state["input"] = f"[redacted: {tool_name} input]"
                        state["output"] = f"[redacted: {tool_name} output]"
                        if isinstance(state.get("metadata"), dict):
                            meta = dict(state["metadata"])
                            if "preview" in meta:
                                meta["preview"] = f"[redacted: {tool_name} preview]"
                            state["metadata"] = meta
                        pdata["state"] = state
                pd["data"] = pdata
                parts.append(pd)
            md["data"] = data
            md["parts"] = parts
            messages.append(md)
        s["messages"] = messages
        out["sessions"].append(s)
    con.close()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", default="opencode_export.json")
    ap.add_argument("--project", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--include-tool-payloads", action="store_true",
                    help="Retain (truncated) tool inputs/outputs. WARNING: may contain secrets.")
    args = ap.parse_args()

    data = export_sessions(
        Path(args.db),
        project=args.project,
        limit=args.limit,
        include_tool_payloads=args.include_tool_payloads,
    )
    Path(args.out).write_text(json.dumps(data, indent=2, default=str))
    n_msg = sum(len(s["messages"]) for s in data["sessions"])
    print(f"exported {len(data['sessions'])} sessions, {n_msg} messages -> {args.out}")


if __name__ == "__main__":
    main()
